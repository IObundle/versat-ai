from versatDefs import *

from functools import reduce


# TODO: Need to properly handle different types and stuff like that.
def TensorSize(tensor: list[int]):
    return reduce(lambda x, y: x * y, tensor) * 4  # 4 because size of float
