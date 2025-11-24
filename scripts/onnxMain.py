import sys
import os
import glob

# Missing split_complex_to_pairs

from versatDefs import *
from memoryAllocator import CalculateMemoryAllocations
from onnxAddOutputsToIntermediate import AddOutputsToEachNode
from onnxOperators import *
from copy import copy

from onnx import shape_inference
from functools import reduce
from pprint import pprint

import struct
import numpy as np
import onnx

import onnxruntime as ort

from onnx import __version__, IR_VERSION
from onnx.defs import onnx_opset_version
from onnx import numpy_helper

# import matplotlib.pyplot as plt


# Nodes have either inputs from other nodes or initializers, which are the constant values embedded in the model.
# If a given node input is a tensor then it is not an input and vice versa.
def GetTensor(model, tensorName):
    for tensor in model.graph.initializer:
        if tensor.name == tensorName:
            return tensor


# TODO: Need to properly handle different types and stuff like that. We might even need to handle padding
def TensorSize(tensor: list[int]):
    return reduce(lambda x, y: x * y, tensor) * 4  # 4 because size of float


def GetValueForDim(dim):
    if dim.WhichOneof("value") == "dim_value":
        return dim.dim_value
    else:
        return dim.dim_param


def GetShape(model, name):
    assert name  # Make sure that we got a name, onnx models contain a lot of members that contain optional names, which might work for some models and not others. Care

    for value in model.graph.output:
        if value.name == name:
            return [GetValueForDim(x) for x in value.type.tensor_type.shape.dim]
    for value in model.graph.input:
        if value.name == name:
            return [GetValueForDim(x) for x in value.type.tensor_type.shape.dim]
    for value in model.graph.value_info:
        if value.name == name:
            return [GetValueForDim(x) for x in value.type.tensor_type.shape.dim]
    for value in model.graph.initializer:
        if value.name == name:
            return [int(x) for x in value.dims]

    # NOTE: We want this function to be able to obtain all the shapes from a given name.
    #       Need to care with the fact that some onnx names are optional. All the names that this function check are mandatory
    #       so this function works fine, just need to make sure that the name that we receive as input actually exists,
    #       and that we did not get it from a optional location, since different graphs might not implement them and this will fail.

    print(model.graph)
    print(f"Could not find shape for {name}")
    assert False


def CalculateOffsetFromSize(sizes: list[int]):
    offset = 0
    result = [offset]
    for size in sizes[:-1]:
        offset += size
        result.append(offset)

    totalSize = offset + sizes[-1]
    return result, totalSize


def EndianessToStructArg(endianess: Endianess):
    endianArg = ""
    if endianess == Endianess.NATIVE:
        endianArg = "@"
    elif endianess == Endianess.LITTLE_ENDIAN:
        endianArg = "<"
    elif endianess == Endianess.BIG_ENDIAN:
        endianArg = ">"
    else:
        assert False

    return endianArg


def PackArrayNoHeader(array, endianess: Endianess = Endianess.NATIVE):
    endianArg = EndianessToStructArg(endianess)

    dtype = array.dtype
    formatArg = "f"
    if dtype == np.int64:
        formatArg = "q"

    data = struct.Struct(f"{endianArg}{formatArg}")
    dataContent = bytearray()
    for x in np.nditer(array):
        dataContent += data.pack(x)

    return dataContent


def PackMultipleArrays(arrayList, endianess: Endianess = Endianess.NATIVE):
    data = bytearray()
    offsets = []
    for array in arrayList:
        offsets.append(len(data))
        data += PackArrayNoHeader(array)

    return PackedArrays(data, offsets)


def RemoveContentExcept(packed: PackedArrays, indexesToPreserve: list[int]):
    content = bytearray()

    newOffsets = []
    for index in indexesToPreserve:
        offset = packed.offsets[index]

        nextOffset = 0
        if index + 1 < len(packed.offsets):
            nextOffset = packed.offsets[index + 1]
        else:
            nextOffset = len(packed.data)

        newOff = len(content)
        content = content + packed.data[offset:nextOffset]
        newOffsets.append(newOff)

    if len(newOffsets):
        return PackedArrays(content, newOffsets)
    else:
        return PackedArrays(bytearray(), [])


def IndexOfNodeThatProducesOutput(cModel, outputName):
    for index, op in enumerate(cModel.operations):
        if outputName == op.output:
            return index
    return None


def GenerateModelFromOnnxModel(onnxModel):
    shaped = shape_inference.infer_shapes(onnxModel)
    cModel = Model(shaped)

    # Need the shape of the inputs and output tensors

    inputNames = []
    for value in onnxModel.graph.input:
        shape = [GetValueForDim(x) for x in value.type.tensor_type.shape.dim]

        if not GetTensor(shaped, value.name):
            inputNames.append(Port(value.name, shape))
    cModel.modelInputs = inputNames

    # Extract all the data that we care about from the graph into a simpler struct for further processing.
    for node in onnxModel.graph.node:
        opType = node.op_type

        # TODO: Need to properly handle the operator not being registered
        operatorSpec = operatorNameToSpec[opType]
        attributesSpec = operatorSpec.attributesDict

        parsedAttributes = {}
        for attribute in node.attribute:
            attributeName = attribute.name

            spec = attributesSpec[attributeName]

            parsedAttribute = None
            if spec.attrType == OnnxAttributeType.INTEGER:
                parsedAttribute = InstantiatedAttribute(spec, int(attribute.i))
            elif spec.attrType == OnnxAttributeType.BOUNDED_INTEGER:
                parsedAttribute = InstantiatedAttribute(spec, int(attribute.i))
            elif spec.attrType == OnnxAttributeType.AXIS_LIST:
                parsedAttribute = InstantiatedAttribute(
                    spec, [int(x) for x in attribute.ints]
                )
            elif spec.attrType == OnnxAttributeType.AXIS_PAIR_LIST:
                parsedAttribute = InstantiatedAttribute(
                    spec, [int(x) for x in attribute.ints]
                )
            elif spec.attrType == OnnxAttributeType.INTEGER_LIST:
                parsedAttribute = InstantiatedAttribute(
                    spec, [int(x) for x in attribute.ints]
                )
            elif spec.attrType == OnnxAttributeType.BOUNDED_STRING:
                parsedAttribute = InstantiatedAttribute(
                    spec, attribute.s.decode("UTF-8")
                )
            else:
                assert False

            parsedAttributes[attribute.name] = parsedAttribute

        inputDimensions = []
        for name in node.input:
            shape = GetShape(shaped, name)
            inputDimensions.append(shape)
            tensor = GetTensor(onnxModel, name)
            if tensor:
                asNpArray = onnx.numpy_helper.to_array(tensor)
                cModel.initializers.append(asNpArray)

        outputDimensions = None
        for output in node.output:
            shape = GetShape(shaped, output)
            outputDimensions = shape

        dataSources = []
        for name in node.input:
            tensor = GetTensor(onnxModel, name)
            source = None
            if tensor:
                source = DataSource(DataSourceType.INITIALIZER, name)
            elif name in [x.name for x in cModel.modelInputs]:
                source = DataSource(DataSourceType.MODEL_INPUT, name)
            else:
                source = DataSource(DataSourceType.NODE_INPUT, name)
            dataSources.append(source)

        outputName = node.output[0]  # Can a node have more than one output?

        op = Operation(
            node.name,
            node.op_type,
            dataSources,
            outputName,
            inputDimensions,
            outputDimensions,
            parsedAttributes,
        )
        cModel.operations.append(op)

    for index, c in enumerate(cModel.operations):
        c.outputIndex = index

    # Calculate initializer position
    initializersSeen = 0
    for index, c in enumerate(cModel.operations):
        for source in c.inputs:
            if source.sourceType == DataSourceType.INITIALIZER:
                source.index = initializersSeen
                initializersSeen += 1
            elif source.sourceType == DataSourceType.MODEL_INPUT:
                for index, port in enumerate(cModel.modelInputs):
                    if port.name == source.name:
                        source.index = index
            else:
                source.index = IndexOfNodeThatProducesOutput(cModel, source.name)

    allInputsShapes = sum([port.shape for port in cModel.modelInputs], [])

    mapped = {}
    for port in cModel.modelInputs:
        for i, name in enumerate(port.shape):
            if type(name) == str:
                mapped[name] = True

    for op in cModel.operations:
        for inputs in op.inputDimensions:
            for i, name in enumerate(inputs):
                if type(name) == str:
                    mapped[name] = True

        for i, name in enumerate(op.outputDimensions):
            if type(name) == str:
                mapped[name] = True

    for name in mapped.keys():
        if name in allInputsShapes:
            print(f"{name} is an input")
        else:
            print(f"{name} is not an input")

    return cModel


def GetModelFreeParameters(cModel):
    params = {}

    for port in cModel.modelInputs:
        for i, name in enumerate(port.shape):
            if type(name) == str:
                params[name] = True

    for op in cModel.operations:
        for inputs in op.inputDimensions:
            for i, name in enumerate(inputs):
                if type(name) == str:
                    params[name] = True

        for i, name in enumerate(op.outputDimensions):
            if type(name) == str:
                params[name] = True

    return params


def RestrictModelFreeParameter(cModel, paramValue):
    # TODO: Currently we force variable sizes to 1 in here
    mapped = {}

    for port in cModel.modelInputs:
        for i, name in enumerate(port.shape):
            if type(name) == str:
                port.shape[i] = mapped.get(name, paramValue)
                mapped[name] = port.shape[i]

    for op in cModel.operations:
        for inputs in op.inputDimensions:
            for i, name in enumerate(inputs):
                if type(name) == str:
                    inputs[i] = mapped.get(name, paramValue)
                    mapped[name] = inputs[i]

        for i, name in enumerate(op.outputDimensions):
            if type(name) == str:
                op.outputDimensions[i] = mapped.get(name, paramValue)
                mapped[name] = op.outputDimensions[i]

    return cModel


def RunModel(model: Model, inputs):
    if not model.sess:
        model.sess = ort.InferenceSession(model.onnxModel.SerializeToString())

    modelInputs = {x.name: y for x, y in zip(model.sess.get_inputs(), inputs)}
    modelOutput = model.sess.run(None, modelInputs)

    mappedOutputs = {x.name: y for x, y in zip(model.sess.get_outputs(), modelOutput)}
    outputs = [None] * len(model.operations)
    for index, op in enumerate(model.operations):
        outputs[index] = mappedOutputs[op.output]

    return ModelRunResult(outputs)


class CDataEmitter:
    def __init__(self):
        self.arrays = []
        self.namedArrays = []

    def EmitNamedArray(self, name, dtype, data):
        self.namedArrays.append(TypedArray(dtype, copy(data), name))

    def EmitArray(self, dtype, data):
        assert isinstance(data, list)
        index = len(self.arrays)

        self.arrays.append(TypedArray(dtype, copy(data)))

        return CDataHandle(index)

    def Representation(self):
        content = ""

        def ItemRepr(item):
            if isinstance(item, CDataHandle):
                return f"temp_{item.index}"
            elif isinstance(item, list):
                return "{" + ",".join([ItemRepr(x) for x in item]) + "}"
            else:
                return str(item)

        for index, tarray in enumerate(self.arrays):
            dtype = tarray.dtype
            data = tarray.data

            content += (
                f"static {dtype} temp_{index}[] = "
                + "{"
                + ",".join(ItemRepr(x) for x in data)
                + "};\n"
            )

        for index, tarray in enumerate(self.namedArrays):
            dtype = tarray.dtype
            data = tarray.data
            name = tarray.name
            amount = len(tarray.data)

            content += (
                f"static {dtype} {name}[{amount}] = "
                + "{"
                + ",".join(ItemRepr(x) for x in data)
                + "};\n"
            )

        return content


# Copied from onnxruntime/tools/python/remove_initializer_from_input.py
def remove_initializer_from_input(model: onnx.ModelProto) -> bool:
    if model.ir_version < 4:
        print(
            "Model with ir_version below 4 requires to include initializer in graph input"
        )
        return False

    inputs = model.graph.input
    name_to_input = {}
    for input in inputs:
        name_to_input[input.name] = input

    modified = False
    for initializer in model.graph.initializer:
        if initializer.name in name_to_input:
            modified = True
            inputs.remove(name_to_input[initializer.name])

    return modified


# TODO: We are starting to accumulate a bunch of config flags and stuff is starting to get out of control
#       We probably want to make a struct that combines all this configuration into a single place and even offer some helper functions to simplify stuff otherwise
#       it becomes clubersome to interact with this. Furthermore we are starting to generate more stuff than we care about and that is not good. Only generate what you need otherwise
#       firmware starts becoming too large and sim time starts becoming problematic and all that stuff.
def GenerateDebug(
    testLocation: str,
    modelName: str,
    binOutputLocation: str,
    sourceOutputLocation: str,
    namespace: str,
    focusLayer: int = None,
    debugSoftware: bool = False,
):
    # TODO: It would be better if we could check all the inputs for correctness.

    if type(namespace) != str or not namespace.isidentifier():
        print("Need a valid namespace name. Needs to follow identifier rules")
        sys.exit(0)
    if len(namespace) > 32:
        print(
            "Error, namespace cannot be larger than 32 bytes. Choose a more reasonable namespace name"
        )
        sys.exit(0)

    print(
        f"onnx.__version__={__version__!r}, opset={onnx_opset_version()}, IR_VERSION={IR_VERSION}"
    )

    # TODO: Only fetching one test, mainly because only a few of the test models actually contain more than 1 test.
    amountOfTests = len(glob.glob(os.path.join(testLocation, "test_data_set_*")))
    print("Tests found", amountOfTests)
    testDataDir = os.path.join(testLocation, "test_data_set_0")
    testModelLocation = os.path.join(testLocation, modelName)

    model = onnx.load(testModelLocation)
    remove_initializer_from_input(model)
    model = AddOutputsToEachNode(model)
    onnx.checker.check_model(model)

    # Perform inference
    sess = ort.InferenceSession(model.SerializeToString())

    inputs = []
    inputs_num = len(glob.glob(os.path.join(testDataDir, "input_*.pb")))
    for i in range(inputs_num):
        input_file = os.path.join(testDataDir, "input_{}.pb".format(i))
        tensor = onnx.TensorProto()
        with open(input_file, "rb") as f:
            tensor.ParseFromString(f.read())
        inputs.append(numpy_helper.to_array(tensor))

    isIntermediate = [False] * len(sess.get_outputs())

    for index, output in enumerate(sess.get_outputs()):
        if "INTERMEDIATE" in output.name:
            isIntermediate[index] = True

    ref_outputs = []
    ref_outputs_num = len(glob.glob(os.path.join(testDataDir, "output_*.pb")))
    for i in range(ref_outputs_num):
        output_file = os.path.join(testDataDir, "output_{}.pb".format(i))
        tensor = onnx.TensorProto()
        with open(output_file, "rb") as f:
            tensor.ParseFromString(f.read())
        ref_outputs.append(numpy_helper.to_array(tensor))

    modelInputs = {x.name: y for x, y in zip(sess.get_inputs(), inputs)}
    modelOutput = sess.run(None, modelInputs)

    properOutputs = []
    for index, output in enumerate(modelOutput):
        if not isIntermediate[index]:
            properOutputs.append(output)

    for ref_o, o in zip(ref_outputs, properOutputs):
        np.testing.assert_allclose(ref_o, o, rtol=1e-05)

    print("Test outputs match with the expected values")

    cModel = GenerateModelFromOnnxModel(model)

    freeParameters = GetModelFreeParameters(cModel)

    if len(freeParameters) > 0:
        # NOTE: Currently we assume that all free parameters are the same value.
        #       All the testbenches that we have work on this assumption and I do not know if we can have a model where this assumption does not hold.
        #       We are also assuming that we only have a single free parameter as input. Need to see a model where this assumption does not hold in order to
        #       then decide on the proper way of progressing.
        # assert len(freeParameters) <= 1

        # We match the parameter to the input and then we instantiate the model with it. No runtime handling of free parameters
        # We do not know it if we need to generate code that can handle this at runtime. Worry about it later, for now we need to make this work on the board first before handling stuff like that.
        freeParameterValue = 1
        for op in cModel.operations:
            for inp in op.inputs:
                if inp.sourceType == DataSourceType.MODEL_INPUT:
                    inputIndex = inp.index
                    inputDims = op.inputDimensions[inputIndex]

                    inputShape = inputs[0].shape

                    for index in range(len(inputShape)):
                        if type(inputDims[index]) == str:
                            freeParameterValue = inputShape[index]

        cModel = RestrictModelFreeParameter(cModel, freeParameterValue)

    # TODO: Implement multiple testcases by running the model multiple times and outputting multiple correct data bins.
    # NOTE: Is it possible for different testcases to generate different amounts of correctData? It shouldn't be possible.
    result = RunModel(cModel, inputs)
    correctData = result.outputs

    packedInputs = PackMultipleArrays(inputs)
    packedCorrectData = PackMultipleArrays(correctData)
    packedInitializers = PackMultipleArrays(cModel.initializers)

    if focusLayer != None and focusLayer >= 0:
        op = cModel.operations[focusLayer]
        cModel.operations = [op]

        op.outputMemoryAddress = MemoryLocation(0, MemoryType.OUTPUT)

        inputIndexes = []
        nodeInputIndexes = []
        initializersIndexes = []

        newInputIndex = 0
        newNodeInputIndex = 0
        newInitializerIndex = 0
        for inp in op.inputs:
            if inp.sourceType == DataSourceType.MODEL_INPUT:
                inputIndexes.append(inp.index)
                inp.index = newInputIndex
                newInputIndex += 1
            if inp.sourceType == DataSourceType.NODE_INPUT:
                nodeInputIndexes.append(inp.index)
                inp.index = newNodeInputIndex
                newNodeInputIndex += 1
            if inp.sourceType == DataSourceType.INITIALIZER:
                initializersIndexes.append(inp.index)
                inp.index = newInitializerIndex
                newInitializerIndex += 1

        op.outputIndex = newNodeInputIndex
        nodeInputIndexes.append(focusLayer)

        packedInputs = RemoveContentExcept(packedInputs, inputIndexes)
        packedCorrectData = RemoveContentExcept(packedCorrectData, nodeInputIndexes)
        packedInitializers = RemoveContentExcept(
            packedInitializers, initializersIndexes
        )

        if len(packedInputs.data) == 0:
            cModel.modelInputs = []

    CalculateMemoryAllocations(cModel)

    for c in cModel.operations:
        print(c.opName, c.inputDimensions)

    debugging = True
    with open(os.path.join(sourceOutputLocation, f"{namespace}_code.c"), "w") as f:
        f.write('#include "versat_private.h"\n')
        f.write('#include "stdint.h"\n\n')

        f.write(f"static int numberLayers = {len(cModel.operations)};\n")

        layerInfo = []

        for index, c in enumerate(cModel.operations):
            outputSize = TensorSize(c.outputDimensions)
            layerInfo.append(
                "{"
                + f'"{OperationToLayerName(c,not debugSoftware)}",{outputSize}'
                + "}"
            )

        f.write("static LayerInfo layers[] = {" + ",".join(layerInfo) + "};\n")

        opcodeToOperationList = {}
        for index, c in enumerate(cModel.operations):
            opcodeToOperationList[c.opName] = opcodeToOperationList.get(
                c.opName, []
            ) + [c]

        emitter = CDataEmitter()

        for opcode in opcodeToOperationList:
            if not IsOperatorRegistered(opcode):
                continue

            operationList = opcodeToOperationList[opcode]

            structs = []
            for index, op in enumerate(operationList):
                structs.append(EmitParameterList(emitter, op))

            emitter.EmitNamedArray(f"{opcode}Infos", f"{opcode}Info", structs)

        content = emitter.Representation()
        f.write(content)

        # Placeholder for operators not yet registered
        for opcode, opList in opcodeToOperationList.items():
            amount = len(opList)

            if IsOperatorRegistered(opcode):
                continue

            content = []
            for op in opList:
                content.append("{}")

            f.write(
                f"{opcode}Info {opcode}Infos[{amount}] = "
                + "{"
                + ",".join(content)
                + "};\n"
            )

        f.write(f"uint64_t {namespace}_time[{len(cModel.operations) + 1}];\n")

        def OutputFunction(debugging, fuctionName, useVersat, measureTime):
            if debugging:
                f.write(
                    f"\nInferenceOutput {fuctionName}(void* outputMemory,void* temporaryMemory,void** inputs,void* modelMemory,void* correctInput)"
                    + "{\n"
                )
            else:
                f.write(
                    f"\nInferenceOutput {fuctionName}(void* outputMemory,void* temporaryMemory,void** inputs,void* modelMemory)"
                    + "{\n"
                )

            opSeen = {}
            for index, c in enumerate(cModel.operations):
                content = []
                for inp in c.inputs:
                    if inp.sourceType == DataSourceType.INITIALIZER:
                        content.append(
                            f"OFFSET_PTR(modelMemory,{packedInitializers.offsets[inp.index]})"
                        )
                    elif inp.sourceType == DataSourceType.MODEL_INPUT:
                        content.append(f"inputs[{inp.index}]")
                    else:
                        if debugging:
                            content.append(
                                f"OFFSET_PTR(correctInput,{packedCorrectData.offsets[inp.index]})"
                            )
                        else:
                            content.append(f"res_{inp.index}")

                outputStr = ""
                if c.outputMemoryAddress.memType == MemoryType.TEMP:
                    outputStr = (
                        f"OFFSET_PTR(temporaryMemory,{c.outputMemoryAddress.offset})"
                    )
                else:
                    outputStr = (
                        f"OFFSET_PTR(outputMemory,{c.outputMemoryAddress.offset})"
                    )

                functionName = OperationToFunctionName(c, useVersat)

                opIndex = opSeen.get(c.opName, -1) + 1
                opSeen[c.opName] = opIndex
                if debugging:
                    f.write(f'  versat_printf("Gonna run layer {index}\\n");\n')

                if measureTime:
                    f.write(f"  {namespace}_time[{index}] = versat_time();\n")

                f.write(
                    f"  void* res_{index} = "
                    + functionName
                    + "("
                    + ",".join(content)
                    + f",{outputStr},{index},&{c.opName}Infos[{opIndex}]);\n"
                )
                if debugging and (IsOperatorRegistered(c.opName)):
                    f.write(
                        f"  AssertAlmostEqual(res_{index},OFFSET_PTR(correctInput,{packedCorrectData.offsets[c.outputIndex]}),{index},&layers[{index}]);\n"
                    )

            if measureTime:
                f.write(
                    f"  {namespace}_time[{len(cModel.operations)}] = versat_time();\n"
                )

            f.write("  return (InferenceOutput){};\n")
            f.write("}\n")

        #              debugging, fuctionName, useVersat, measureTime
        OutputFunction(False, f"{namespace}_SoftwareRunInference", False, True)
        OutputFunction(False, f"{namespace}_VersatRunInference", True, True)
        OutputFunction(True, f"{namespace}_DebugRunInference", not debugSoftware, False)

    correctDataSize = 0
    inputSize = 0

    if debugging:
        correctDataSize = len(packedCorrectData.data)
        inputSize = len(cModel.modelInputs)

    with open(os.path.join(sourceOutputLocation, f"{namespace}_modelInfo.h"), "w") as f:
        f.write("#pragma once\n")

        f.write('#include "versat_ai.h"\n\n')

        totalInputSize = 0
        inputOffsets = [0]
        inputSizes = [0]

        if len(cModel.modelInputs) > 0:
            inputSizes = [TensorSize(x.shape) for x in cModel.modelInputs]
            inputOffsets, totalInputSize = CalculateOffsetFromSize(inputSizes)

        f.write(f"static const int {namespace}_INPUT_SIZE[] = " + "{")
        f.write(",".join([str(x) for x in inputSizes]))
        f.write("};\n")

        f.write(f"static const int {namespace}_INPUT_OFFSET[] = " + "{")
        f.write(",".join([str(x) for x in inputOffsets]))
        f.write("};\n\n")

        f.write(f"extern uint64_t {namespace}_time[];\n")

        f.write(
            f"InferenceOutput {namespace}_SoftwareRunInference(void *outputMemory, void *temporaryMemory,void **inputs, void *modelMemory);\n"
            f"InferenceOutput {namespace}_VersatRunInference(void *outputMemory, void *temporaryMemory,void **inputs, void *modelMemory);\n"
            f"InferenceOutput {namespace}_DebugRunInference(void *outputMemory, void *temporaryMemory,void **inputs, void *modelMemory,void *correctInput);\n\n"
        )

        f.write(f"static TestModelInfo {namespace}_ModelInfo = " + "{\n")
        f.write(f"  .outputSize = {cModel.outputMemoryNeeded},\n")
        f.write(f"  .tempSize = {cModel.tempMemoryNeeded},\n")
        f.write(f"  .modelSize = {len(packedInitializers.data)},\n")
        f.write(f"  .correctSize = {correctDataSize},\n")
        f.write(f"  .totalInputSize = {totalInputSize},\n")

        f.write(f'  .nameSpace = "{namespace}",\n')

        f.write(f"  .inputCount = {inputSize},\n")
        f.write(f"  .inputSizes = {namespace}_INPUT_SIZE,\n")
        f.write(f"  .inputOffsets = {namespace}_INPUT_OFFSET,\n")

        f.write(f"  .operatorCount = {len(cModel.operations)},\n")
        f.write(f"  .timeMeasurements = {namespace}_time,\n")

        f.write(f"  .softwareInferenceFunction = {namespace}_SoftwareRunInference,\n")
        f.write(f"  .versatInferenceFunction = {namespace}_VersatRunInference,\n")
        f.write(f"  .debugInferenceFunction = {namespace}_DebugRunInference\n")
        f.write("};\n")
    try:
        os.makedirs(binOutputLocation)
    except:
        pass

    if debugging:
        with open(
            os.path.join(binOutputLocation, f"{namespace}_inputs.bin"), "wb"
        ) as f:
            f.write(packedInputs.data)

        with open(
            os.path.join(binOutputLocation, f"{namespace}_correctOutputs.bin"), "wb"
        ) as f:
            f.write(packedCorrectData.data)

    with open(os.path.join(binOutputLocation, f"{namespace}_model.bin"), "wb") as f:
        f.write(packedInitializers.data)


if __name__ == "__main__":
    if len(sys.argv) < 6:
        print(
            "Error, script requires 5 parameters, <testLocation> <modelName> <binOutputLocation> <sourceOutputLocation> <namespaceName>"
        )
        sys.exit(0)
    GenerateDebug(
        sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], None, namespaceName
    )

# TODO: Need to take care with alignment issues. Embedded usually cannot handle misaligned data.

# TODO: Need to start giving NAMESPACE names to C stuff, this code is supposed to be easy to integrate anywhere.

# TODO: Need to also output the input file so we can start testing things and implementing the operators in C code.
#       Need to output parameters. Do not know the approach that we should take here.
#         Should we generate optimized functions for a given set of parameters?
#         Or should we just embed the data in source code and let runtime deal with it?
#         Or should we just pack it into a file and load at runtime? (Should only be a few kbs).
#       Even if we embed the data, I think it would be helpful to make a Conv2D especial function.
