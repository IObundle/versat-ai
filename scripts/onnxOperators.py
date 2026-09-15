from typing import Callable
from dataclasses import dataclass, field
from copy import copy

from versatDefs import (
    Operation,
    OnnxAttribute,
    OnnxAttributeType,
    OnnxOperatorSpec,
    BroadcastType,
    PaddingType,
)
from enum import Enum, auto

# TODO: I eventually want to start generating the C structs from the emitters defined here. Really cumbersome to have to match
#      the emitter code with the C code,.

# TODO: Because Onnx supports variable sized tensors, we might want to start moving the tensors shape calculations to runtime.
#      For now this is fine because most models do not have dynamic tensor shapes, but eventually need to do this.


def ExtendShape(shapeList, dimensions):
    res = copy(shapeList)
    if len(shapeList) < dimensions:
        for i in range(dimensions - len(shapeList)):
            res = [1] + res
    return res


def BroadCastShape(op0, op1):
    if len(op0) != len(op1):
        length = max(len(op0), len(op1))
        op0 = ExtendShape(op0)
        op1 = ExtendShape(op1)

    res = []
    for a, b in zip(op0, op1):
        res.append(max(a, b))
    return res


def MakeAttrBoundedString(allowedStringValues: list[str], default: str = None):
    return OnnxAttribute(OnnxAttributeType.BOUNDED_STRING, allowedStringValues, default)


def MakeAttrBoundedInteger(allowedIntegerValues: list[int], default: int = None):
    return OnnxAttribute(
        OnnxAttributeType.BOUNDED_INTEGER, allowedIntegerValues, default
    )


def MakeAttrIntegerList(defaultValue):
    return OnnxAttribute(OnnxAttributeType.INTEGER_LIST, [], defaultValue)


def MakeAttrAxisList(defaultValue):
    return OnnxAttribute(OnnxAttributeType.AXIS_LIST, [], defaultValue)


def MakeAttrAxisPairList(defaultValue):
    return OnnxAttribute(OnnxAttributeType.AXIS_PAIR_LIST, [], defaultValue)


def MakeAttrInteger(defaultValue):
    return OnnxAttribute(OnnxAttributeType.INTEGER, [], defaultValue)


def MakeAttrFloat(defaultValue):
    return OnnxAttribute(OnnxAttributeType.FLOAT, [], defaultValue)


# Some attributes have defaults that depend on the operator (like the size of the spatial axis and such)
# This function essentially instantiates default values such that outer code does not have to check if an attributes exists or not.
def GetAttributesForOperator(op: Operation) -> dict[str, any]:
    opName = op.opName

    if opName not in operatorNameToSpec:
        return None

    opSpec = operatorNameToSpec[opName]

    # TODO: We can actually remove this and the function. All we need is to use the data that we have to figure out whether we need to use a default attribute value or a value that is contained inside the operator.

    res = {}
    for name, attrType in opSpec.attributesDict.items():
        if name in op.parsedAttributes:
            res[name] = op.parsedAttributes[name]
        else:
            if callable(attrType.defaultValue):
                print("Callable default type")
                assert False  # TODO: Need to implement this. Call the function with the operation and implement these functions to return the default value for the operation

            # For spatial axis attributes, calculate spatialAxes from output.
            if (
                attrType.attrType == OnnxAttributeType.AXIS_LIST
                or attrType.attrType == OnnxAttributeType.AXIS_PAIR_LIST
            ):
                spatialAxes = 2 * (len(op.outputDimensions[0]) - 2)
                trueDefaultValue = [attrType.defaultValue] * spatialAxes

                res[name] = trueDefaultValue
            else:
                res[name] = attrType.defaultValue

    return res


# This must match with the result of the EmitFunction
# It must also be ordered. Any "static" info comes first and all the variable info must come last
addStructure = [
    ["maxDims", "int"],
    ["firstInputDims", ("int64_t", "maxDims")],
    ["secondInputDims", ("int64_t", "maxDims")],
    ["broadCastedShape", ("int64_t", "maxDims")],
]


def EmitAdd(emitter, op: Operation):
    maxDims = max(len(op.inputDimensions[0]), len(op.inputDimensions[1]))
    op0 = ExtendShape(op.inputDimensions[0], maxDims)
    op1 = ExtendShape(op.inputDimensions[1], maxDims)

    broadCastedShape = BroadCastShape(op0, op1)

    emitter.I32(maxDims)
    emitter.I64Array(op0, maxDims)
    emitter.I64Array(op1, maxDims)
    emitter.I64Array(broadCastedShape, maxDims)


reluStructure = [["dims", "int"], ["inputDims", ("int64_t", "dims")]]


def EmitRelu(emitter, op: Operation):
    emitter.I32(len(op.inputDimensions[0]))
    emitter.I64Array(op.inputDimensions[0])


maxPoolStructure = [
    ["dims", "int"],
    ["kernelSize", "int"],
    ["strideSize", "int"],
    ["padsSize", "int"],
    ["padding", "PaddingType"],
    ["kernelDims", ("int", "kernelSize")],
    ["strideDims", ("int", "strideSize")],
    ["padsDims", ("int", "padsSize")],
    ["inputDims", ("int64_t", "dims")],
    ["outputDims", ("int64_t", "dims")],
]


def EmitMaxPool(emitter, op: Operation):
    attr = GetAttributesForOperator(op)

    dims = len(op.inputDimensions[0])
    stride = attr["strides"]
    kernel = attr["kernel_shape"]
    pads = attr["pads"]
    padType = attr["auto_pad"]

    padAsEnum = PaddingType[padType]

    emitter.I32(dims)
    emitter.I32(len(kernel))
    emitter.I32(len(stride))
    emitter.I32(len(pads))
    emitter.I32(padAsEnum.value)
    emitter.I32Array(kernel)
    emitter.I32Array(stride)
    emitter.I32Array(pads)

    emitter.I64Array(op.inputDimensions[0])
    emitter.I64Array(op.outputDimensions[0])


convStructure = [
    ["dims", "int"],
    ["group", "int"],
    ["featureMaps", "int"],
    ["kernelSize", "int"],
    ["strideSize", "int"],
    ["dilationsSize", "int"],
    ["padsSize", "int"],
    ["isNHWC", "int"],
    ["padding", "PaddingType"],
    ["kernelDims", ("int", "kernelSize")],
    ["strideDims", ("int", "strideSize")],
    ["dilationsDims", ("int", "dilationsSize")],
    ["padsDims", ("int", "padsSize")],
    ["inputDims", ("int64_t", "dims")],
    ["outputDims", ("int64_t", "dims")],
]


def EmitConv(emitter, op: Operation):
    attr = GetAttributesForOperator(op)

    d = op.inputDimensions[0]
    dims = len(d)
    kernel = attr["kernel_shape"]
    stride = attr["strides"]
    dilations = attr["dilations"]
    pads = attr["pads"]
    group = attr["group"]
    padType = attr["auto_pad"]
    isNHWC = attr["isNHWC"]

    padAsEnum = PaddingType[padType]
    featureMaps = op.inputDimensions[1][0]

    emitter.I32(dims)
    emitter.I32(group)
    emitter.I32(featureMaps)
    emitter.I32(len(kernel))
    emitter.I32(len(stride))
    emitter.I32(len(dilations))
    emitter.I32(len(pads))
    emitter.I32(1 if isNHWC else 0)
    emitter.I32(padAsEnum.value)

    emitter.I32Array(kernel)
    emitter.I32Array(stride)
    emitter.I32Array(dilations)
    emitter.I32Array(pads)
    emitter.I64Array(d)
    emitter.I64Array(op.outputDimensions[0])


reshapeStructure = [
    ["numberInputDims", "int"],
    ["numberShapeDims", "int"],
    ["inputDims", ("int64_t", "numberInputDims")],
]


def EmitReshape(emitter, op: Operation):
    op0 = op.inputDimensions[0]
    dimIn = len(op.inputDimensions[0])
    dimOut = op.inputDimensions[1][0]

    emitter.I32(dimIn)
    emitter.I32(dimOut)
    emitter.I64Array(op0)


matMulStructure = [
    ["isBTransposed", "int"],
    ["numberInputADims", "int"],
    ["numberInputBDims", "int"],
    ["numberOutputDims", "int"],
    ["inputADims", ["int64_t", "numberInputADims"]],
    ["inputBDims", ["int64_t", "numberInputBDims"]],
    ["outputDims", ["int64_t", "numberOutputDims"]],
]

matMulAttributes = {
    "isBTransposed": MakeAttrInteger(0),
}


def EmitMatMul(emitter, op: Operation):
    attr = GetAttributesForOperator(op)

    isBTransposed = attr["isBTransposed"]

    op0 = op.inputDimensions[0]
    op1 = op.inputDimensions[1]
    res = op.outputDimensions[0]

    emitter.I32(isBTransposed)

    emitter.I32(len(op0))
    emitter.I32(len(op1))
    emitter.I32(len(res))

    emitter.I64Array(op0)
    emitter.I64Array(op1)
    emitter.I64Array(res)


softmaxStructure = [
    ["numberInputDims", "int"],
    ["axis", "int"],
    ["inputDims", ["int64_t", "numberInputDims"]],
]


def EmitSoftmax(emitter, op: Operation):
    attr = GetAttributesForOperator(op)

    dims = len(op.inputDimensions[0])
    axis = attr["axis"]

    emitter.I32(dims)
    emitter.I32(axis)
    emitter.I64Array(op.inputDimensions[0])


transposeStructure = [
    ["numberInputDims", "int"],
    ["permSize", "int"],
    ["inputDims", ["int64_t", "numberInputDims"]],
    ["perm", ["int64_t", "permSize"]],
]


def EmitTranspose(emitter, op: Operation):
    dims = len(op.inputDimensions[0])
    attr = GetAttributesForOperator(op)
    perm = attr["perm"]

    emitter.I32(dims)
    emitter.I32(len(perm))
    emitter.I64Array(op.inputDimensions[0])
    emitter.I64Array(perm)


batchNormalizationStructure = [
    ["numberInputDims", "int"],
    ["epsilon", "float"],
    ["momentum", "float"],
    ["inputDims", ["int64_t", "numberInputDims"]],
]


def EmitBatchNormalization(emitter, op: Operation):
    dims = len(op.inputDimensions[0])

    attr = GetAttributesForOperator(op)
    epsilon = attr["epsilon"]
    momentum = attr["momentum"]

    emitter.I32(dims)
    emitter.F32(epsilon)
    emitter.F32(momentum)
    emitter.I64Array(op.inputDimensions[0])


dropoutStructure = [
    ["numberInputDims", "int"],
    ["ratio", "float"],
    ["inputDims", ["int64_t", "numberInputDims"]],
]


def EmitDropout(emitter, op: Operation):
    dims = len(op.inputDimensions[0])

    emitter.I32(dims)
    emitter.F32(0.0)
    emitter.I64Array(op.inputDimensions[0])


lrnStructure = [
    ["numberInputDims", "int"],
    ["alpha", "float"],
    ["beta", "float"],
    ["bias", "float"],
    ["size", "int"],
    ["inputDims", ["int64_t", "numberInputDims"]],
]


def EmitLRN(emitter, op: Operation):
    dims = len(op.inputDimensions[0])
    attr = GetAttributesForOperator(op)

    alpha = attr["alpha"]
    beta = attr["beta"]
    bias = attr["bias"]
    size = attr["size"]

    emitter.I32(dims)
    emitter.F32(alpha)
    emitter.F32(beta)
    emitter.F32(bias)
    emitter.I32(size)

    emitter.I64Array(op.inputDimensions[0])


gemmStructure = [
    ["numberInputDims", "int"],
    ["alpha", "float"],
    ["beta", "float"],
    ["transA", "int"],
    ["transB", "int"],
    ["aDims", ["int64_t", "numberInputDims"]],
    ["bDims", ["int64_t", "numberInputDims"]],
    ["cDims", ["int64_t", "numberInputDims"]],
]


def EmitGemm(emitter, op: Operation):
    dims = len(op.inputDimensions[0])
    attr = GetAttributesForOperator(op)

    alpha = attr["alpha"]
    beta = attr["beta"]
    transA = attr["transA"]
    transB = attr["transB"]

    emitter.I32(dims)
    emitter.F32(alpha)
    emitter.F32(beta)
    emitter.I32(transA)
    emitter.I32(transB)

    cShape = None
    if len(op.inputDimensions) > 2:
        cShape = op.inputDimensions[2]

    assert cShape  # TODO: Need to handle this being optional
    if len(cShape) == 1:
        cShape = [1, cShape[0]]

    emitter.I64Array(op.inputDimensions[0])
    emitter.I64Array(op.inputDimensions[1])
    emitter.I64Array(cShape)


padStructure = [
    ["dims", "int"],
    ["mode", "int"],
    ["constant", "float"],
    ["inputDims", ["int64_t", "dims"]],
    ["outputDims", ["int64_t", "dims"]],
    ["pad", ["int64_t", "dims * 2"]],
]


def EmitPad(emitter, op: Operation):
    dims = len(op.inputDimensions[0])
    attr = GetAttributesForOperator(op)

    emitter.I32(dims)

    if attr["mode"] == "constant":
        emitter.I32(0)
    if attr["mode"] == "reflect":
        emitter.I32(1)
    if attr["mode"] == "edge":
        emitter.I32(2)

    emitter.F32(attr["value"])

    emitter.I64Array(op.inputDimensions[0])
    emitter.I64Array(op.outputDimensions[0])
    emitter.I64Array(attr["pads"])


fixPadStructure = [
    ["dims", "int"],
    ["constant", "float"],
    ["outputDims", ["int64_t", "dims"]],
    ["pad", ["int64_t", "dims * 2"]],
]


def EmitFixPad(emitter, op: Operation):
    dims = len(op.outputDimensions[0])
    attr = GetAttributesForOperator(op)

    emitter.I32(dims)
    emitter.F32(attr["value"])

    emitter.I64Array(op.outputDimensions[0])
    emitter.I64Array(attr["pads"])


def IsOperatorRegistered(opName: str):
    return opName in operatorNameToSpec


def EmitParameterList(emitter, op: Operation):
    global operatorNameToSpec
    spec = operatorNameToSpec.get(op.opName, None)

    if not spec:
        print(
            f"Operator {op.opName} is not registered and no implementation exists for it"
        )
        print(f"Know operators: {operatorNameToSpec.keys()}")
    elif spec.emitFunction:
        return spec.emitFunction(emitter, op)
    else:
        return "{}"


convAttributes = {
    "auto_pad": MakeAttrBoundedString(
        ["NOTSET", "SAME_UPPER", "SAME_LOWER", "VALID"], "NOTSET"
    ),
    "dilations": MakeAttrAxisList(1),
    "group": MakeAttrInteger(1),
    "kernel_shape": MakeAttrIntegerList(None),
    "pads": MakeAttrAxisPairList(0),
    "strides": MakeAttrAxisList(1),
    "isNHWC": MakeAttrInteger(0),
}

maxPoolAttributes = {
    "auto_pad": MakeAttrBoundedString(
        ["NOTSET", "SAME_UPPER", "SAME_LOWER", "VALID"], "NOTSET"
    ),
    # "ceil_mode": MakeAttrInteger(0),
    # "dilations": MakeAttrAxisList(1),
    "kernel_shape": MakeAttrIntegerList(None),
    "pads": MakeAttrAxisPairList(0),
    # "storage_order": MakeAttrBoundedInteger([0, 1], 0),
    "strides": MakeAttrAxisList(1),
}

averagePoolAttributes = {
    "auto_pad": MakeAttrBoundedString(
        ["NOTSET", "SAME_UPPER", "SAME_LOWER", "VALID"], "NOTSET"
    ),
    # "ceil_mode": MakeAttrInteger(0),
    # "dilations": MakeAttrAxisList(1),
    "kernel_shape": MakeAttrIntegerList(None),
    "pads": MakeAttrAxisPairList(0),
    # "storage_order": MakeAttrBoundedInteger([0, 1], 0),
    "strides": MakeAttrAxisList(1),
}

softmaxAttributes = {"axis": MakeAttrInteger(-1)}

transposeAttributes = {
    "perm": MakeAttrIntegerList(
        lambda x: x
    )  # TODO: Implement this when needed. Basically receive an Operation and return the default value
}

batchNormalizationAttributes = {
    "epsilon": MakeAttrFloat(1e-5),
    "momentum": MakeAttrFloat(0.9),
    "training_mode": MakeAttrInteger(0),
}

lrnAttributes = {
    "alpha": MakeAttrFloat(0.0001),
    "beta": MakeAttrFloat(0.75),
    "bias": MakeAttrFloat(1.0),
    "size": MakeAttrInteger(None),
}

gemmAttributes = {
    "alpha": MakeAttrFloat(1.0),
    "beta": MakeAttrFloat(1.0),
    "transA": MakeAttrInteger(0),
    "transB": MakeAttrInteger(0),
}

padAttributes = {
    "mode": MakeAttrBoundedString(["constant", "reflect", "edge"], "constant"),
    "pads": MakeAttrAxisPairList(0),
    "value": MakeAttrFloat(0.0),
}

fixPadAttributes = {
    "pads": MakeAttrAxisPairList(0),
    "value": MakeAttrFloat(0.0),
}

dropoutAttributes = {"ratio": MakeAttrFloat(0.5)}


def GetOperatorSpec(opName):
    global operatorNameToSpec
    return operatorNameToSpec[opName]


def OperationToFunctionName(op: Operation, useVersat: bool):
    spec = GetOperatorSpec(op.opName)

    decider = "Versat" if useVersat and spec.supportedByVersat else "Software"

    name = op.opName
    if op.opName == "Conv":
        if len(op.inputs) == 3:
            name = "ConvWithBias"

    return f"{decider}_{name}"


def OperationToLayerName(op: Operation, useVersat: bool):
    spec = GetOperatorSpec(op.opName)

    if useVersat and spec.supportedByVersat:
        return f"Versat_{op.opName}"
    else:
        return op.opName


def GetAllOperatorSpecs():
    return operatorNameToSpec


# Register new operators here
# Remember, currently we only care about supporting up to version 7 operators.

# name,emitFunction,attributesDict,supportedByVersat,broadcastType
operatorNameToSpec = {}
operatorNameToSpec["Add"] = OnnxOperatorSpec("Add", 0, EmitAdd, addStructure, {}, True)
operatorNameToSpec["Relu"] = OnnxOperatorSpec(
    "Relu", 1, EmitRelu, reluStructure, {}, True
)
operatorNameToSpec["MaxPool"] = OnnxOperatorSpec(
    "MaxPool",
    2,
    EmitMaxPool,
    maxPoolStructure,
    maxPoolAttributes,
    True,
    BroadcastType.NO_BROADCAST,
    0.001,
)
operatorNameToSpec["AveragePool"] = OnnxOperatorSpec(
    "AveragePool", 3, EmitMaxPool, maxPoolStructure, averagePoolAttributes, True
)
operatorNameToSpec["Conv"] = OnnxOperatorSpec(
    "Conv", 4, EmitConv, convStructure, convAttributes, True
)
operatorNameToSpec["Reshape"] = OnnxOperatorSpec(
    "Reshape", 5, EmitReshape, reshapeStructure, {}, True
)
operatorNameToSpec["MatMul"] = OnnxOperatorSpec(
    "MatMul", 6, EmitMatMul, matMulStructure, matMulAttributes, True
)
operatorNameToSpec["Softmax"] = OnnxOperatorSpec(
    "Softmax", 7, EmitSoftmax, softmaxStructure, softmaxAttributes, True
)
operatorNameToSpec["Transpose"] = OnnxOperatorSpec(
    "Transpose", 8, EmitTranspose, transposeStructure, transposeAttributes, False
)
operatorNameToSpec["BatchNormalization"] = OnnxOperatorSpec(
    "BatchNormalization",
    9,
    EmitBatchNormalization,
    batchNormalizationStructure,
    batchNormalizationAttributes,
    True,
)

operatorNameToSpec["Dropout"] = OnnxOperatorSpec(
    "Dropout", 10, EmitDropout, dropoutStructure, dropoutAttributes, True
)

# NOTE: We could improve LRN precision by using more internal memory but we are kinda
#       trying to keep memory usage low (while making sure that everything works fine)
#       and later on we can handle the tradeoff between performance vs memory vs precision.
operatorNameToSpec["LRN"] = OnnxOperatorSpec(
    "LRN",
    11,
    EmitLRN,
    lrnStructure,
    lrnAttributes,
    True,
    BroadcastType.NO_BROADCAST,
    0.1,
)
operatorNameToSpec["Gemm"] = OnnxOperatorSpec(
    "Gemm", 12, EmitGemm, gemmStructure, gemmAttributes, True
)

operatorNameToSpec["Pad"] = OnnxOperatorSpec(
    "Pad", 13, EmitPad, padStructure, padAttributes, False
)

operatorNameToSpec["FixPad"] = OnnxOperatorSpec(
    "FixPad", 254, EmitFixPad, fixPadStructure, fixPadAttributes, False
)

operatorNameToSpec["NIL"] = OnnxOperatorSpec(
    "NIL", 255, lambda *args: None, [], {}, False
)
