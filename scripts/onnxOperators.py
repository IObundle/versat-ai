from typing import Callable
from dataclasses import dataclass, field
from copy import copy

from versatDefs import (
    Operation,
    InstantiatedAttribute,
    OnnxAttribute,
    OnnxAttributeType,
    OnnxOperatorSpec,
)
from enum import Enum, auto

# TODO: I eventually want to start generating the C structs from the emitters defined here. Really clubersome to have to match
#      the emitter code with the C code, any change requires to carefully interact with

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


# Some attributes have defaults that depend on the operator (like the size of the spatial axis and such)
# This function essentially instantiates default values such that outer code does not have to check if an attributes exists or not.
def GetAttributesForOperator(op: Operation) -> dict[str, InstantiatedAttribute]:
    opName = op.opName

    if not opName in operatorNameToSpec:
        return None

    opSpec = operatorNameToSpec[opName]

    # TODO: We can actually remove this and the function. All we need is to use the data that we have to figure out whether we need to use a default attribute value or a value that is contained inside the operator.

    res = {}
    for name, attrType in opSpec.attributesDict.items():
        if name in op.parsedAttributes:
            res[name] = op.parsedAttributes[name]
        else:
            # For spatial axis attributes, calculate spatialAxes from output.
            if (
                attrType.attrType == OnnxAttributeType.AXIS_LIST
                or attrType.attrType == OnnxAttributeType.AXIS_PAIR_LIST
            ):
                spatialAxes = len(op.outputDimensions) - 2
                trueDefaultValue = [attrType.defaultValue] * spatialAxes

                res[name] = InstantiatedAttribute(attrType, trueDefaultValue)
            else:
                res[name] = InstantiatedAttribute(attrType, attrType.defaultValue)

    return res


def EmitAdd(emitter, op: Operation):
    maxDims = max(len(op.inputDimensions[0]), len(op.inputDimensions[1]))

    op0 = ExtendShape(op.inputDimensions[0], maxDims)
    op1 = ExtendShape(op.inputDimensions[1], maxDims)

    broadCastedShape = BroadCastShape(op0, op1)

    aux_0 = emitter.EmitArray("int64_t", op0)
    aux_1 = emitter.EmitArray("int64_t", op1)
    aux_2 = emitter.EmitArray("int64_t", broadCastedShape)

    return [maxDims, aux_0, aux_1, aux_2]


def EmitRelu(emitter, op: Operation):
    aux = emitter.EmitArray("int64_t", op.inputDimensions[0])
    dims = len(op.inputDimensions[0])
    return [dims, aux]


def EmitMaxPool(emitter, op: Operation):
    dims = len(op.inputDimensions[0])
    inputShape = emitter.EmitArray("int64_t", op.inputDimensions[0])
    outputShape = emitter.EmitArray("int64_t", op.outputDimensions)

    attr = GetAttributesForOperator(op)

    kernel = attr["kernel_shape"].value
    kernelShape = emitter.EmitArray("int", kernel)

    dil = attr["dilations"].value
    dilShape = emitter.EmitArray("int", dil)

    return [dims, inputShape, outputShape, len(kernel), kernelShape, len(dil), dilShape]


def EmitConv(emitter, op: Operation):
    inputDim = len(op.inputDimensions[0])
    inputShape = emitter.EmitArray("int64_t", op.inputDimensions[0])

    kernelDim = len(op.inputDimensions[1])
    kernelShape = emitter.EmitArray("int64_t", op.inputDimensions[1])

    outDim = len(op.outputDimensions)
    outShape = emitter.EmitArray("int64_t", op.outputDimensions)

    return [inputDim, inputShape, kernelDim, kernelShape, outDim, outShape]


def EmitReshape(emitter, op: Operation):
    op0 = op.inputDimensions[0]
    dimIn = len(op.inputDimensions[0])
    dimOut = op.inputDimensions[1][0]

    aux_0 = emitter.EmitArray("int64_t", op0)

    return [aux_0, dimIn, dimOut]


def EmitMatMul(emitter, op: Operation):
    op0 = op.inputDimensions[0]
    op1 = op.inputDimensions[1]
    res = [op0[0], op1[1]]

    aux_0 = emitter.EmitArray("int64_t", op0)
    aux_1 = emitter.EmitArray("int64_t", op1)
    aux_2 = emitter.EmitArray("int64_t", res)

    return [aux_0, len(op0), aux_1, len(op1), aux_2, len(res)]


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
}

maxPoolAttributes = {
    "auto_pad": MakeAttrBoundedString(
        ["NOTSET", "SAME_UPPER", "SAME_LOWER", "VALID"], "NOTSET"
    ),
    "ceil_mode": MakeAttrInteger(0),
    "dilations": MakeAttrAxisList(1),
    "kernel_shape": MakeAttrIntegerList(None),
    "pads": MakeAttrAxisPairList(0),
    "storage_order": MakeAttrBoundedInteger([0, 1], 0),
    "strides": MakeAttrAxisList(1),
}


def GetOperatorSpec(opName):
    global operatorNameToSpec
    return operatorNameToSpec[opName]


# Register new operators here
operatorNameToSpec = {}
operatorNameToSpec["Add"] = OnnxOperatorSpec("Add", EmitAdd, True, False, [], True)
operatorNameToSpec["Conv"] = OnnxOperatorSpec(
    "Conv", EmitConv, False, False, convAttributes
)
operatorNameToSpec["Relu"] = OnnxOperatorSpec("Relu", EmitRelu, False, False, [], True)
operatorNameToSpec["MaxPool"] = OnnxOperatorSpec(
    "MaxPool",
    EmitMaxPool,
    False,
    False,
    maxPoolAttributes,
)
operatorNameToSpec["Reshape"] = OnnxOperatorSpec(
    "Reshape", EmitReshape, False, False, [], True
)
operatorNameToSpec["MatMul"] = OnnxOperatorSpec("MatMul ", EmitMatMul, False, False)
