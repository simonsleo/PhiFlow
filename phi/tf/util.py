# coding=utf-8
import tensorflow as tf
from phi.math.nd import *
from phi.math.container import *
from tensorflow.python import pywrap_tensorflow


def placeholder(shape, dtype=np.float32, name=None):
    shapes, reassemble = disassemble(shape)
    zeros = [tf.placeholder(dtype, shape, name) for shape in shapes]
    return reassemble(zeros)

def variable(container, dtype=np.float32, name=None, trainable=True):
    initial_values, reassemble = disassemble(container)
    vars = [tf.Variable(val, name=name, dtype=dtype, trainable=trainable) for val in initial_values]
    return reassemble(vars)



def group_normalization(x, group_count, eps=1e-5):
    batch_size, H, W, C = tf.shape(x)
    gamma = tf.Variable(np.ones([1,1,1,C]), dtype=tf.float32, name="GN_gamma")
    beta = tf.Variable(np.zeros([1,1,1,C]), dtype=tf.float32, name="GN_beta")
    x = tf.reshape(x, [batch_size, group_count, H, W, C // group_count])
    mean, var = tf.nn.moments(x, [2, 3, 4], keep_dims=True)
    x = (x - mean) / tf.sqrt(var + eps)
    x = tf.reshape(x, [batch_size, H, W, C])
    return x * gamma + beta


def residual_block(y, nb_channels, kernel_size=(3, 3), _strides=(1, 1), activation=tf.nn.leaky_relu,
                   _project_shortcut=False, padding="SYMMETRIC", name=None, training=False, trainable=True, reuse=tf.AUTO_REUSE):
    shortcut = y

    if isinstance(kernel_size, int):
        kernel_size = (kernel_size, kernel_size)

    pad1 = [(kernel_size[0] - 1) // 2, kernel_size[0] // 2]
    pad2 = [(kernel_size[1] - 1) // 2, kernel_size[1] // 2]

    # down-sampling is performed with a stride of 2
    y = tf.pad(y, [[0,0], pad1, pad2, [0,0]], mode=padding)
    y = tf.layers.conv2d(y, nb_channels, kernel_size=kernel_size, strides=_strides, padding='valid',
             name=None if name is None else name+"/conv1", trainable=trainable, reuse=reuse)
    # y = tf.layers.batch_normalization(y, name=None if name is None else name+"/norm1", training=training, trainable=trainable, reuse=reuse)
    y = activation(y)

    y = tf.pad(y, [[0,0], pad1, pad2, [0,0]], mode=padding)
    y = tf.layers.conv2d(y, nb_channels, kernel_size=kernel_size, strides=(1, 1), padding='valid',
             name=None if name is None else name + "/conv2", trainable=trainable, reuse=reuse)
    # y = tf.layers.batch_normalization(y, name=None if name is None else name+"/norm2", training=training, trainable=trainable, reuse=reuse)

    # identity shortcuts used directly when the input and output are of the same dimensions
    if _project_shortcut or _strides != (1, 1):
        # when the dimensions increase projection shortcut is used to match dimensions (done by 1×1 convolutions)
        # when the shortcuts go across feature maps of two sizes, they are performed with a stride of 2
        shortcut = tf.pad(shortcut, [[0,0], pad1, pad2, [0,0]], mode=padding)
        shortcut = tf.layers.conv2d(shortcut, nb_channels, kernel_size=(1, 1), strides=_strides, padding='valid',
                        name=None if name is None else name + "/convid", trainable=trainable, reuse=reuse)
        # shortcut = tf.layers.batch_normalization(shortcut, name=None if name is None else name+"/normid", training=training, trainable=trainable, reuse=reuse)

    y += shortcut
    y = activation(y)

    return y


def residual_block_1d(y, nb_channels, kernel_size=(3,), _strides=(1,), activation=tf.nn.leaky_relu,
                   _project_shortcut=False, padding="SYMMETRIC", name=None, training=False, trainable=True, reuse=tf.AUTO_REUSE):
    shortcut = y

    if isinstance(kernel_size, int):
        kernel_size = (kernel_size,)

    pad1 = [(kernel_size[0] - 1) // 2, kernel_size[0] // 2]

    # down-sampling is performed with a stride of 2
    y = tf.pad(y, [[0,0], pad1, [0,0]], mode=padding)
    y = tf.layers.conv1d(y, nb_channels, kernel_size=kernel_size, strides=_strides, padding='valid',
             name=None if name is None else name+"/conv1", trainable=trainable, reuse=reuse)
    # y = tf.layers.batch_normalization(y, name=None if name is None else name+"/norm1", training=training, trainable=trainable, reuse=reuse)
    y = activation(y)

    y = tf.pad(y, [[0,0], pad1, [0,0]], mode=padding)
    y = tf.layers.conv1d(y, nb_channels, kernel_size=kernel_size, strides=(1,), padding='valid',
             name=None if name is None else name + "/conv2", trainable=trainable, reuse=reuse)
    # y = tf.layers.batch_normalization(y, name=None if name is None else name+"/norm2", training=training, trainable=trainable, reuse=reuse)

    # identity shortcuts used directly when the input and output are of the same dimensions
    if _project_shortcut or _strides != (1,):
        # when the dimensions increase projection shortcut is used to match dimensions (done by 1×1 convolutions)
        # when the shortcuts go across feature maps of two sizes, they are performed with a stride of 2
        shortcut = tf.pad(shortcut, [[0,0], pad1, [0,0]], mode=padding)
        shortcut = tf.layers.conv1d(shortcut, nb_channels, kernel_size=(1, 1), strides=_strides, padding='valid',
                        name=None if name is None else name + "/convid", trainable=trainable, reuse=reuse)
        # shortcut = tf.layers.batch_normalization(shortcut, name=None if name is None else name+"/normid", training=training, trainable=trainable, reuse=reuse)

    y += shortcut
    y = activation(y)

    return y


def istensor(object):
    if isinstance(object, StaggeredGrid):
        object = object.staggered
    return isinstance(object, tf.Tensor)



def conv_function(scope, constants_file=None):
    if constants_file is not None:
        reader = pywrap_tensorflow.NewCheckpointReader(constants_file)
        def conv(n, filters, kernel_size, strides=[1,1,1,1], padding="VALID", activation=None, name=None, kernel_initializer=None):
            assert name != None
            kernel = reader.get_tensor("%s/%s/kernel"%(scope,name))
            assert kernel.shape[-1] == filters, "Expected %d filters but loaded kernel has shape %s for conv %s" % (kernel_size, kernel.shape, name)
            if isinstance(kernel_size, int):
                assert kernel.shape[0] == kernel.shape[1] == kernel_size
            else:
                assert kernel.shape[0:2] == kernel_size
            if isinstance(strides, int):
                strides = [1, strides, strides, 1]
            elif len(strides) == 2:
                strides = [1, strides[0], strides[1], 1]
            n = tf.nn.conv2d(n, kernel, strides=strides, padding=padding.upper(), name=name)
            if activation is not None:
                n = activation(n)
            n = tf.nn.bias_add(n, reader.get_tensor("%s/%s/bias"%(scope,name)))
            return n
    else:
        def conv(n, filters, kernel_size, strides=(1,1), padding="valid", activation=None, name=None, kernel_initializer=None):
            with tf.variable_scope(scope):
                return tf.layers.conv2d(n, filters=filters, kernel_size=kernel_size, strides=strides, padding=padding,
                                        activation=activation, name=name, reuse=tf.AUTO_REUSE, kernel_initializer=kernel_initializer)
    return conv