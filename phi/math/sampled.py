from phi import math
from phi.math.nd import *


def grid(griddef, points, values=None, duplicate_handling='mean', staggered=False):
    valid_indices = math.to_int(math.floor(points))
    valid_indices = math.minimum(math.maximum(0, valid_indices), griddef.dimensions-1)
    # Correct format for math.scatter
    valid_indices = batch_indices(valid_indices)

    # Assume no out of bounds indices exist in the list
    if values is None:
        ones = math.expand_dims(math.prod(math.ones_like(points), axis=-1), axis=-1)

        return math.scatter(valid_indices, ones, griddef.shape(1), duplicates_handling=duplicate_handling)
    else:
        if staggered:
            dims = range(len(griddef.dimensions))
            # Staggered grids only for vector fields
            assert values.shape[-1] == len(dims)
            
            result = []
            oneD_ones = math.unstack(math.ones_like(values), axis=-1)[0]
            staggered_shape = [i+1 for i in griddef.dimensions]
            for d in dims: 
                staggered_offset = math.stack([(0.5 * oneD_ones if i == d else 0.0 * oneD_ones) for i in dims], axis=-1)

                indices = math.to_int(math.floor(points + staggered_offset))
                
                valid_indices = math.maximum(0, math.minimum(indices, griddef.dimensions))
                valid_indices = batch_indices(valid_indices)

                # No need to manually 'mean', Out of Bounds particles aren't handled here, need to implement that somewhere else.
                values_d = math.expand_dims(math.unstack(values, axis=-1)[d], axis=-1)
                result.append(math.scatter(valid_indices, values_d, [indices.shape[0]] + staggered_shape + [1], duplicates_handling='mean'))
            
            return StaggeredGrid(math.concat(result, axis=-1))

        else:
            return math.scatter(valid_indices, values, griddef.shape(math.shape(values)[-1]), duplicates_handling=duplicate_handling)


def active_centers(array):
    assert array.shape[-1] == 1
    index_array = []
    for batch in range(array.shape[0]):
        indices = math.where(array[batch,...,0] > 0)
        index_array.append(indices)
    try:
        index_array = math.stack(index_array)
    except ValueError:
        raise ValueError("all arrays in the batch must have the same number of active cells.")
    return index_array + 0.5


def random_grid_to_coords(array, particles_per_cell=1):
    assert array.shape[-1] == 1
    index_array = []
    
    for batch in range(array.shape[0]):
        indices = math.where(array[batch,...,0] > 0)
        indices = math.to_float(indices)

        temp = []
        for _ in range(particles_per_cell):
            # Uniform distribution over cell
            temp.append(indices + math.random_like(indices))
        index_array.append(math.concat(temp, axis=0))

    try:
        index_array = math.stack(index_array)
    except ValueError:
        raise ValueError("all arrays in the batch must have the same number of active cells.")
    
    return index_array


def grid_to_particles(griddef, points, values, staggered=False):
    if staggered:
        values = values.staggered
        dims = range(len(griddef.dimensions))
        # Staggered grids only for vector fields
        assert values.shape[-1] == len(dims)

        result = []
        oneD_ones = math.unstack(math.ones_like(points), axis=-1)[0]
        for d in dims:
            staggered_offset = math.stack([(0.0 * oneD_ones if i == d else -0.5 * oneD_ones) for i in dims], axis=-1)

            indices = (points + staggered_offset)
            values_d = math.expand_dims(math.unstack(values, axis=-1)[d], axis=-1)

            result.append(math.resample(values_d, indices, boundary="REPLICATE"))

        return math.concat(result, axis=-1)

    else:
        return math.resample(values, points-0.5, boundary="REPLICATE")


def batch_indices(indices):
    """
Reshapes the indices, such that aside from indices they also contain batch number. For example the entry (32, 40) as coordinates of batch 2 will become (2, 32, 40).
Transform shape (b, p, d) to (b, p, d+1) where batch size is b, number of particles is p and number of dimensions is d. 
    """
    batch_size = indices.shape[0]
    out_spatial_rank = len(indices.shape) - 2
    out_spatial_size = math.shape(indices)[1:-1]

    batch_ids = math.reshape(math.range_like(indices, batch_size), [batch_size] + [1] * out_spatial_rank)
    tile_shape = math.pad(out_spatial_size, [[1,0]], constant_values=1)
    batch_ids = math.expand_dims(math.tile(batch_ids, tile_shape), axis=-1)

    return math.concat((batch_ids, indices), axis=-1)