from typing import Callable
from dataclasses import dataclass, field
from enum import Enum, auto

import numpy as np


@dataclass
class PackedArrays:
    data: bytes
    offsets: list[int]


class Endianess(Enum):
    NATIVE = auto()
    LITTLE_ENDIAN = auto()
    BIG_ENDIAN = auto()


class DataSourceType(Enum):
    MODEL_INPUT = auto()
    NODE_INPUT = auto()
    INITIALIZER = auto()


@dataclass
class DataSource:
    sourceType: DataSourceType
    name: str

    # Computed afterwards. Easier to store directly.
    index: int = -1
    correctInputIndex: int = -1


class MemoryType(Enum):
    TEMP = auto()
    OUTPUT = auto()


@dataclass
class MemoryLocation:
    offset: int
    memType: MemoryType


class OnnxAttributeType(Enum):
    INTEGER = auto()
    BOUNDED_INTEGER = auto()
    INTEGER_LIST = auto()
    AXIS_LIST = auto()
    AXIS_PAIR_LIST = auto()
    BOUNDED_STRING = auto()


@dataclass
class OnnxAttribute:
    attrType: OnnxAttributeType
    allowedValues: list[any]
    defaultValue: any


@dataclass
class InstantiatedAttribute:
    attributeSpec: OnnxAttribute
    value: any

    def __repr__(self):
        return str(self.value)


@dataclass
class Operation:
    # Data extracted from the model
    nodeName: str
    opName: str
    inputs: list[DataSource]
    output: str  # For now we are assuming that nodes only contain one output. Most graphs appear to follow this principle, even if the output is used by multiple nodes, the node itself only appaears to contain one. Maybe more exotic operations shatter this notion but will deal with them when they appear.
    inputDimensions: list[list[int | str]]
    outputDimensions: list[int | str]
    parsedAttributes: dict[str, InstantiatedAttribute] = None

    # Data computed from extracted model.
    outputMemoryAddress: MemoryLocation = (
        None  # Address at runtime. We precalculate it, we do not allocate memory at runtime.
    )


class BroadcastType(Enum):
    NO_BROADCAST = auto()
    UNIDIRECTIONAL = auto()
    MULTIDIRECTIONAL = auto()


@dataclass
class OnnxOperatorSpec:
    name: str
    emitFunction: Callable
    attributesDict: dict[str, OnnxAttribute] = field(default_factory=dict)
    generateVersatCode: bool = False
    broadcastType: BroadcastType = BroadcastType.NO_BROADCAST


@dataclass
class Port:
    name: str
    shape: list[int]
    isOriginal: bool = (
        True  # In order to extract data from nodes, we add custom output ports. This variable is true only for the ports that are original, no modification made
    )


# A more useful representation for our use cases than having to interact with the onnx model directly
@dataclass
class Model:
    onnxModel: any  # Already transformed to ouput intermediate results
    sess: any = None
    modelOutputs: list[str] = None
    isModelOutputIntermediate: list[bool] = None
    modelInputs: list[Port] = field(default_factory=list)
    initializers: list[np.array] = field(default_factory=list)
    operations: list[Operation] = field(default_factory=list)
    tempMemoryNeeded: int = -1
    outputMemoryNeeded: int = -1


@dataclass
class ModelRunResult:
    outputs: list[np.array]  # Maps operation to its output.


@dataclass
class MemoryAllocation:
    firstCycle: int
    lastCycle: int
    amount: int
