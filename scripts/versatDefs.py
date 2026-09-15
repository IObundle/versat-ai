import sys

from typing import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from pprint import pformat
from copy import deepcopy

import onnx
from onnx import TensorProto, version_converter
from onnx.helper import (
    make_model,
    make_node,
    make_graph,
    make_tensor_value_info,
    make_opsetid,
)
from onnx.checker import check_model
import onnxruntime as ort


import numpy as np


class OptimizationRules(Enum):
    # Pad stuff
    EXTRACT_CONV_PAD = auto()  # Conv(NotSetPadding) := Pad -> Conv(NoPadding)
    PUSH_PAD_OVER_RELU = auto()  # N -> Pad := Pad -> N. For some N
    PUSH_PAD_OVER_CONV = auto()  # Conv -> Pad := Pad -> Conv -> FixPad
    PUSH_PAD_OVER_FIXPAD = auto()  # FixPad -> Pad := Pad -> FixPad
    JOIN_PADS = auto()  # Pad -> Pad := Pad
    # FixPad stuff
    JOIN_FIXPADS = auto()
    # Add stuff
    ADD_REMOVE_BOTH_TRANSPOSE = auto()
    # Transpose stuff
    JOIN_TRANSPOSE = auto()  # Transpose -> Transpose := Transpose
    PUSH_TRANSPOSE_OVER_RELU = (
        auto()
    )  # N -> Transpose := Transpose -> N. For some N that do not require special treatment
    PUSH_TRANSPOSE_OVER_FIXPAD = auto()
    PUSH_TRANSPOSE_OVER_PAD = auto()
    FOLD_TRANSPOSE = auto()  # Initializer -> Transpose := Initializer
    # MatMul stuff
    MATMUL_TRANSPOSE = auto()  # Data,Data -> MatMul(bIsTransposed = False) :=
    # Data,(Data -> Transpose) -> MatMul(bIsTransposed = True)
    # Conv Stuff
    CONV_NCHW_TO_NHWC = auto()


@dataclass
class PackedArrays:
    data: bytes
    offsets: list[int]


class Endianess(Enum):
    NATIVE = auto()  # NATIVE
    LITTLE_ENDIAN = auto()
    BIG_ENDIAN = auto()


class DataSourceType(Enum):
    UNCONNECTED = auto()
    MODEL_INPUT = auto()
    NODE_INPUT = auto()
    INITIALIZER = auto()


@dataclass
class CDataHandle:
    index: int


@dataclass
class TypedArray:
    dtype: str
    data: list[any]
    name: str = None


def NpArrayToIdentifier(npArray):
    ident = None
    if npArray.dtype == np.float32:
        ident = 0
        for index in np.ndindex(npArray.shape):
            ident += npArray[index]

    if npArray.dtype == np.int64:
        ident = 0
        for index in np.ndindex(npArray.shape):
            ident += npArray[index]

    if ident is None:
        print(npArray.dtype)
        assert False

    return str(npArray.shape) + "_" + str(ident)


# A source of data. Initializer data is stored in here. ModelInputs data for validation are also stored.
# Node data only contains the index of the outputting node. Valid data can be obtained by getting node
# and getting the correctOutputData
@dataclass
class DataSource:
    sourceType: DataSourceType
    name: str  # Only used during graph construction to bridge between onnx data and ours. Could probably remove this.

    index: int = -1
    data: np.array = None
    tensorDims: list[int | str] | None = None  # Not always guaranteed to exist.

    def __repr__(self):
        res = str(self.sourceType)

        if self.index >= 0:
            res += "_" + str(self.index)

        if self.data is not None:
            res += "_" + NpArrayToIdentifier(self.data)

        if self.tensorDims is not None:
            res += "_" + str(self.tensorDims)

        return res


def MakeNodeInput(name, nodeIndex: int):
    out = DataSource(DataSourceType.NODE_INPUT, name, nodeIndex)
    return out


def CopyDataSource(inp: DataSource):
    dataCopy = None
    if inp.data is not None:
        dataCopy = np.copy(inp.data)
    tensorDims = None
    if inp.tensorDims is not None:
        tensorDims = list(inp.tensorDims)

    out = DataSource(inp.sourceType, inp.name, inp.index, dataCopy, tensorDims)
    return out


class MemoryType(Enum):
    TEMP = auto()
    OUTPUT = auto()


@dataclass
class MemoryLocation:
    offset: int
    memType: MemoryType

    computedSize: int = -1


class OnnxAttributeType(Enum):
    INTEGER = auto()
    FLOAT = auto()
    BOUNDED_INTEGER = auto()
    INTEGER_LIST = auto()
    AXIS_LIST = auto()
    AXIS_PAIR_LIST = auto()
    BOUNDED_STRING = auto()
    ENUM = auto()


class PaddingType(Enum):
    NOTSET = 0
    SAME_UPPER = 1
    SAME_LOWER = 2
    VALID = 3


@dataclass
class OnnxAttribute:
    attrType: OnnxAttributeType
    allowedValues: list[any]
    defaultValue: any


# Graph stuff: Every operation (a node in the graph) contains an index
# that is not guaranteed to match with the position of the node in the
# graph array.  This index is the value that is stored inside the data
# sources. Because graph operations can add and remove nodes, this
# makes sure that we do not need to update every node everytime we
# make a change.
# For model inputs and initializers the index is the position on the array
# since these do not change or are removed.

# NOTE: Currently the only data that is always correct is inputs.
#       inputDimensions, outputDimensions and correctOutputData can be momentarily wrong
#       or not set. This usually happens during graph operations and normally they are resolved
#       as soon as possible.
#
#       Inputs and inputDimensions kinda have duplicated data that we might eventually remove.
#       Since inputs are the source of truth in relation to graph stuff, we might just remove
#       inputDimensions and have everything work from inputs.


@dataclass(slots=False)
class Operation:
    # Data extracted from the model
    nodeName: str
    opName: str
    nodeIndex: int
    inputs: list[DataSource]
    outputName: str  # For now we are assuming that nodes only contain one output. Most graphs appear to follow this principle, even if the output is used by multiple nodes, the node itself only appears to contain one. Maybe more exotic operations shatter this notion but will deal with them when they appear.

    inputDimensions: list[list[int | str]]
    outputDimensions: list[list[int | str]]
    parsedAttributes: dict[str, any] = field(default_factory=dict)

    # Data used to check operation correctness (TODO: Only one since we only support 1 output per node right now)
    correctOutputData: np.array = None

    # Data computed after graph operations
    outputMemoryAddress: MemoryLocation = (
        None  # Address at runtime. We precalculate it, we do not allocate memory at runtime.
    )

    def __repr__(self):
        dictCont = deepcopy(vars(self))

        if dictCont["correctOutputData"] is not None:
            dictCont["correctOutputData"] = NpArrayToIdentifier(
                dictCont["correctOutputData"]
            )

        return str(dictCont)


Operation_NIL = Operation("", "NIL", -1, [], "", [], [], {})


class BroadcastType(Enum):
    NO_BROADCAST = auto()
    UNIDIRECTIONAL = auto()
    MULTIDIRECTIONAL = auto()


@dataclass
class OnnxOperatorSpec:
    name: str
    index: int  # Must be different for each operator.
    emitFunction: Callable
    emitStructure: list = field(default_factory=list)
    attributesDict: dict[str, OnnxAttribute] = field(default_factory=dict)
    supportedByVersat: bool = False
    broadcastType: BroadcastType = BroadcastType.NO_BROADCAST
    floatPrecision: float = 0.001


@dataclass
class InputData:
    name: str
    shape: list[int | str]
    isOriginal: bool = (
        True  # In order to extract data from nodes, we add custom output ports. This variable is true only for the ports that are original, no modification made
    )


@dataclass
class Port:
    index: int
    port: int


@dataclass
class GenericDataSource:
    dims: list[int]
    data: np.array

    def Valid(self):
        valid = self.data is not None and self.dims is not None
        return valid


def ConvertOnnxPadToNumpyPad(onnxPad):
    # Onnx Pad is start0,start1,start2,end0,end1,end2,...
    # Numpy pad is start0,end0,start1,end1,start2,end2,...

    numpyPad = []
    numberOfAxis = len(onnxPad) // 2

    for x in range(0, numberOfAxis):
        numpyPad.append([onnxPad[x], onnxPad[x + numberOfAxis]])

    return numpyPad


def ReverseNpPad(inp: np.ndarray, padding):
    shape = inp.shape

    slices = []
    for i, dim in enumerate(shape):
        start = padding[i][0]
        end = dim - padding[i][1]

        slices.append(slice(start, end))

    reverse = inp[tuple(slices)]
    return reverse


def IsSourceNode(inp: DataSource, nodeIndexToCheck: int):
    if inp.sourceType == DataSourceType.NODE_INPUT and inp.index == nodeIndexToCheck:
        return True
    return False


# A more useful representation for our use cases than having to interact with the onnx model directly
@dataclass
class Model:
    # TODO: This might need to go. During graph operations we might change stuff and eventually have to
    modelInputs: list[InputData] = field(default_factory=list)

    operations: list[Operation] = field(default_factory=list)

    nextInitializerIndex: int = 0
    nextOperationIndex: int = 0

    # Calculated after parameter instantiation and other model operations that change operations are performed
    tempMemoryNeeded: int = -1
    outputMemoryNeeded: int = -1

    anyFailedUpdates: bool = False

    def GetGenericDataSource(self, src: DataSource):
        dims = None
        data = None

        if src.sourceType == DataSourceType.NODE_INPUT:
            outputNode = self.GetOperationByIndexOrFail(src.index)
            data = outputNode.correctOutputData
            dims = list(outputNode.outputDimensions[0])
        else:
            data = src.data
            dims = src.tensorDims

            if dims is None and data is not None:
                dims = [int(x) for x in data.shape]

        return GenericDataSource(dims, data)

    # If we already have A -> B:x and want to insert in the middle C (A -> C:y and C -> B:x)
    def InsertBefore(self, B: Operation, x: int, C: Operation, y: int):
        C.inputs[y] = CopyDataSource(B.inputs[x])
        B.inputs[x] = MakeNodeInput(B.inputs[x].name, C.nodeIndex)

        # self.UpdateNodeData(C)
        # self.UpdateNodeData(B)

    # If we have A -> Graph and want to insert C after (A -> C:y -> Graph)
    def InsertAfter(self, A: Operation, C: Operation, y: int):
        nodesAndPortIndexes = self.GetOutputNodesAndPortIndexes(A, 0)

        # self.UpdateNodeData(A)

        if len(nodesAndPortIndexes) == 0:
            # There is no output node, we are in a model output
            C.inputs[y] = MakeNodeInput("", A.nodeIndex)
            # self.UpdateNodeData(C)

        for B in self.operations:
            if B == C or B == A:
                continue
            for index, inp in enumerate(B.inputs):
                if IsSourceNode(inp, A.nodeIndex):
                    self.InsertBefore(B, index, C, y)

    # Swap X -> A -> B -> Y to become X -> B -> A -> Y
    # Y is not guaranteed to exist. Only X,A and B
    # We only care about shape preserving operations right now.
    def Swap(self, A: Operation, B: Operation):
        assert len(A.inputs) == 1
        assert len(B.inputs) == 1

        # A is before B.
        if not IsSourceNode(B.inputs[0], A.nodeIndex):
            if IsSourceNode(A.inputs[0], B.nodeIndex):
                A, B = B, A
            else:
                assert False and "B and A are not connected directly. Cannot Swap"

        XInput = deepcopy(A.inputs[0])
        AInput = deepcopy(B.inputs[0])
        YList = self.GetOutputNodesAndPortIndexes(B, 0)

        A.inputs = [MakeNodeInput("", B.nodeIndex)]
        B.inputs = [XInput]

        # self.UpdateNodeData(B)
        # self.UpdateNodeData(A)

        for node, portIndex in YList:
            node.inputs = deepcopy(node.inputs)
            node.inputs[portIndex] = MakeNodeInput("", A.nodeIndex)
            # self.UpdateNodeData(node)

    # Returns X for X -> start:inputPort
    def GetInputNode(self, start: Operation, inputPort: int):
        if inputPort >= len(start.inputs):
            return Operation_NIL

        dataSource = start.inputs[inputPort]

        if dataSource.sourceType != DataSourceType.NODE_INPUT:
            return Operation_NIL

        opIndex = dataSource.index
        node = self.GetOperationByIndexOrFail(opIndex)
        return node

    # Output mostly ignored for now
    def GetOutputNodesAndPortIndexes(self, source: Operation, outputPort: int):
        res = []
        for op in self.operations:
            for index, inp in enumerate(op.inputs):
                if IsSourceNode(inp, source.nodeIndex):
                    res.append([op, index])
                    break

        return res

    def GetAllModelOutputNodes(self):
        modelOutput = []
        for op in self.operations:
            outputsNodes = self.GetOutputNodesAndPortIndexes(op, 0)
            if len(outputsNodes) == 0:
                modelOutput.append(op)

        return modelOutput

    # TODO: Input size is stupid
    def AddOperation(self, opType, inputSize):
        opIndex = self.NextOperationIndex()
        name = f"ADDED_{opIndex}"
        outputName = f"GENERATED_OUTPUT_{opIndex}"
        inputs = [DataSource(DataSourceType.UNCONNECTED, "")] * inputSize
        inputDims = [None] * inputSize
        outputDims = [None] * inputSize
        newOp = Operation(
            name, opType, opIndex, inputs, outputName, inputDims, outputDims
        )
        self.operations.append(newOp)

        return newOp

    def PreserveOnlyOne(self, toPreserve):
        for inp in toPreserve.inputs:
            gen = self.GetGenericDataSource(inp)

            inp.sourceType = DataSourceType.INITIALIZER
            inp.index = self.NextInitializerIndex()
            inp.data = deepcopy(gen.data)

        self.operations = [toPreserve]

    def RemoveOperationKeepData(self, toRemove: Operation):
        data = DataSource(DataSourceType.INITIALIZER, "", self.NextInitializerIndex())
        data.data = deepcopy(toRemove.correctOutputData)

        allOutputNodes = self.GetOutputNodesAndPortIndexes(toRemove, 0)

        # print(allOutputNodes)
        for node, port in allOutputNodes:
            node.inputs[port] = deepcopy(data)

        self.operations.remove(toRemove)

    def RemoveOperationDoNotKeepData(self, toRemove: Operation):
        if len(toRemove.inputs) == 1:
            # A -> B -> C
            # When we remove B, we have to connect all the Cs to A.
            ASrc = toRemove.inputs[0]
            allCNodes = self.GetOutputNodesAndPortIndexes(toRemove, 0)

            for node, port in allCNodes:
                node.inputs[port] = ASrc
                # self.UpdateNodeData(node)
        else:
            assert False

        self.operations.remove(toRemove)

    # As long as the input data is correct, this should work.
    # Onnx suported operators are updated using onnxruntime
    # Our operators require custom code.
    def UpdateNodeData(self, op: Operation):
        opType = op.opName

        if opType == "NIL":
            return

        # FixPad is a custom non onnx operator that we have.
        # Not supported by onnxruntime
        if opType == "FixPad":
            src = self.GetGenericDataSource(op.inputs[0])
            pads = op.parsedAttributes["pads"]

            npPads = ConvertOnnxPadToNumpyPad(pads)

            # We fixup padding by reversing and padding again.
            # Easiest way of doing this and we only care about correctness right now.
            reversedPad = ReverseNpPad(src.data, npPads)
            paddedAgain = np.pad(reversedPad, npPads)

            op.inputDimensions = [deepcopy(src.dims)]
            op.outputDimensions = [deepcopy(src.dims)]
            op.correctOutputData = paddedAgain
        else:
            inputData = []
            for inp in op.inputs:
                genericForm = self.GetGenericDataSource(inp)

                if not genericForm.Valid():
                    print("Cannot update node since input data does not exist")
                    print(inp.dims)
                    assert False

                inputData.append(genericForm)

            finalData = deepcopy(inputData)

            # Since transposed matmul is not something that is suppported by onnx, need to
            # fake it. The output must remain the same meaning that we just need to invert
            # the transposition before passing it to onnxruntime
            parsedAttributes = deepcopy(op.parsedAttributes)

            if op.opName == "MatMul" and parsedAttributes.get("isBTransposed", False):
                inputData[1].data = np.transpose(inputData[1].data)
                inputData[1].dims = [int(x) for x in inputData[1].data.shape]
                del parsedAttributes["isBTransposed"]

            transposeOutput = False
            if op.opName == "Conv" and parsedAttributes.get("isNHWC", False):
                transposeOutput = True
                # Input should be in NCHW format meaning that we have to make it NCHW

                inputData[0].data = np.transpose(inputData[0].data, axes=(0, 3, 1, 2))
                inputData[0].dims = [int(x) for x in inputData[0].data.shape]
                del parsedAttributes["isNHWC"]

            tensors = []
            inputs = []
            for i, data in enumerate(inputData):
                inputName = f"IN_{i}"

                # TODO: Properly handle this. Need to add more stuff to the node specs.
                tensorType = TensorProto.FLOAT
                if op.opName == "Reshape" and i == 1:
                    tensorType = TensorProto.INT64

                # print(op.opName,tensorType)
                tensor = make_tensor_value_info(inputName, tensorType, data.dims)

                inputs.append(inputName)
                tensors.append(tensor)

            outputTensorDim = None
            if op.opName == "Reshape":
                outputTensorDim = []

            outputTensor = make_tensor_value_info(
                "OUT", TensorProto.FLOAT, outputTensorDim
            )

            node = make_node(op.opName, inputs, ["OUT"], **parsedAttributes)

            graph = make_graph([node], "simpleTest", tensors, [outputTensor])
            onnx_model = make_model(graph, opset_imports=[make_opsetid("", 7)])
            onnx_model = version_converter.convert_version(onnx_model, 7)
            shaped = onnx.shape_inference.infer_shapes(onnx_model)

            op.inputDimensions = [None for x in inputData]
            op.outputDimensions = [None]
            try:
                check_model(shaped)
                # Otherwise even a small change could trigger our asserts.
                sess_options = ort.SessionOptions()
                sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                sess_options.intra_op_num_threads = 1
                sess_options.inter_op_num_threads = 1
                sess_options.add_session_config_entry("session.disable_prepacking", "1")

                sess = ort.InferenceSession(shaped.SerializeToString(), sess_options)
                modelInputs = {
                    x.name: y.data for x, y in zip(sess.get_inputs(), inputData)
                }
                modelOutput = sess.run(None, modelInputs)

                # Try to make sure that onnxruntime produces the same data for the same inputs.

                if transposeOutput:
                    modelOutput[0] = np.transpose(modelOutput[0], axes=(0, 2, 3, 1))

                # Also update input dimensions since they might go out of sync from inputs
                op.inputDimensions = [deepcopy(x.dims) for x in finalData]
                op.correctOutputData = modelOutput[0]

                op.outputDimensions = [None]
                op.outputDimensions[0] = [int(x) for x in modelOutput[0].shape]
            except:
                print(f"Failed to update node of index: {op.nodeIndex} {op.opName}")
                anyFailedUpdates = True

    def NextInitializerIndex(self):
        res = self.nextInitializerIndex
        self.nextInitializerIndex += 1
        return res

    def NextOperationIndex(self):
        res = self.nextOperationIndex
        self.nextOperationIndex += 1
        return res

    def GetOperationByIndexOrFail(self, index):
        for op in self.operations:
            if op.nodeIndex == index:
                return op
        assert False


@dataclass
class ModelRunResult:
    outputs: list[np.array]  # Maps operation to its output.


@dataclass
class MemoryAllocation:
    firstCycle: int
    lastCycle: int
    amount: int

    # Calculated by memory allocator function
    offset: int = -1
