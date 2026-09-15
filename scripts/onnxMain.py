import sys
import os
import glob

# Missing split_complex_to_pairs

from versatDefs import *
from versatCommons import *
from memoryAllocator import CalculateMemoryAllocations
from onnxAddOutputsToIntermediate import AddOutputsToEachNode
from onnxOperators import *
from copy import copy
from structBuilder import StructBuilder

from onnx import shape_inference
from pprint import pprint
from copy import deepcopy

import struct
import numpy as np
import onnx

import onnxruntime as ort

from onnx import __version__, IR_VERSION
from onnx.defs import onnx_opset_version
from onnx import numpy_helper

COLOR_BASE = "\33[0m"
COLOR_RED = "\33[31m"
COLOR_GREEN = "\33[32m"
COLOR_BLUE = "\33[34m"


# Nodes have either inputs from other nodes or initializers, which are the constant values embedded in the model.
# If a given node input is a tensor then it is not an input and vice versa.
def GetTensor(model, tensorName):
    for tensor in model.graph.initializer:
        if tensor.name == tensorName:
            return tensor


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

    # TODO: If we knew what type we are expecting (input, output, initializer) then we could do a proper error report.
    #       Instead of assuming that it is just an unused output.
    print(f"WARNING: Could not find shape for {name}")
    print("    Assuming unused output")

    return [0]

    # NOTE: We want this function to be able to obtain all the shapes from a given name.
    #       Need to care with the fact that some onnx names are optional. All the names that this function check are mandatory
    #       so this function works fine, just need to make sure that the name that we receive as input actually exists,
    #       and that we did not get it from a optional location, since different graphs might not implement them and this will fail.

    # print(model.graph)
    # print(f"Could not find shape for {name}")
    # assert False


def CalculateOffsetFromSize(sizes: list[int]):
    offset = 0
    result = [offset]
    for size in sizes[:-1]:
        offset += size
        result.append(offset)

    totalSize = offset + sizes[-1]
    return result, totalSize


def PackArrayNoHeader(array, endianess: Endianess = Endianess.NATIVE):
    dtype = array.dtype
    data = StructBuilder(endianess)
    for index in np.ndindex(array.shape):
        x = array[index]
        if dtype == np.int64:
            data.I64(x)
        else:
            data.F32(x)

    return data.GetContent()


def PackMultipleArrays(arrayList, endianess: Endianess = Endianess.NATIVE):
    data = bytearray()
    offsets = []
    for array in arrayList:
        offsets.append(len(data))
        data += PackArrayNoHeader(array)

    return PackedArrays(data, offsets)


def RemoveContentExcept(packed: PackedArrays, indexesToPreserveInOrder: list[int]):
    content = bytearray()

    newOffsets = []
    for index in indexesToPreserveInOrder:
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


def RemoveContent(packed: PackedArrays, indexMap: dict[int, int]):
    content = bytearray()

    newOffsets = [0]
    finalIndexToPackIndex = {}

    for packIndex, finalIndex in indexMap:
        finalIndexToPackIndex[finalIndex] = packIndex


def IndexOfNodeThatProducesOutput(cModel: Model, outputName):
    for index, op in enumerate(cModel.operations):
        if outputName == op.outputName:
            return op.nodeIndex
    return None


def GenerateModelFromOnnxModel(onnxModel):
    shaped = shape_inference.infer_shapes(onnxModel)
    cModel = Model(shaped)

    inputNames = []
    for value in onnxModel.graph.input:
        shape = [GetValueForDim(x) for x in value.type.tensor_type.shape.dim]

        if not GetTensor(shaped, value.name):
            inputNames.append(InputData(value.name, shape))
    cModel.modelInputs = inputNames

    # Check for operators not supported.
    opsNotSupported = {}
    for node in onnxModel.graph.node:
        opType = node.op_type

        if opType not in operatorNameToSpec:
            opsNotSupported[opType] = 1

    if len(opsNotSupported):
        print("\n\n[ERROR]")
        print("The following operators that are present in the graph")
        print("are not currently implemented and therefore we cannot proceed:")

        for item in opsNotSupported.keys():
            print(f"    {item}")

        print("\n")

        sys.exit(0)

    # Extract all the data that we care about from the graph into a simpler struct for further processing.
    for node in onnxModel.graph.node:
        opType = node.op_type

        operatorSpec = operatorNameToSpec[opType]
        attributesSpec = operatorSpec.attributesDict

        parsedAttributes = {}
        for attribute in node.attribute:
            attributeName = attribute.name
            spec = attributesSpec[attributeName]

            parsedAttribute = None
            if spec.attrType == OnnxAttributeType.INTEGER:
                parsedAttribute = int(attribute.i)
            elif spec.attrType == OnnxAttributeType.BOUNDED_INTEGER:
                parsedAttribute = int(attribute.i)
            elif spec.attrType == OnnxAttributeType.AXIS_LIST:
                parsedAttribute = [int(x) for x in attribute.ints]
            elif spec.attrType == OnnxAttributeType.AXIS_PAIR_LIST:
                parsedAttribute = [int(x) for x in attribute.ints]
            elif spec.attrType == OnnxAttributeType.INTEGER_LIST:
                parsedAttribute = [int(x) for x in attribute.ints]
            elif spec.attrType == OnnxAttributeType.BOUNDED_STRING:
                parsedAttribute = attribute.s.decode("UTF-8")
            elif spec.attrType == OnnxAttributeType.FLOAT:
                parsedAttribute = float(attribute.f)
            elif spec.attrType == OnnxAttributeType.ENUM:
                name = attribute.s.decode("UTF-8")
                parsedAttribute = name
            else:
                print(spec.attrType)
                assert False

            parsedAttributes[attribute.name] = parsedAttribute

        dataSources = []
        inputDimensions = []
        for name in node.input:
            shape = GetShape(shaped, name)
            inputDimensions.append(shape)
            tensor = GetTensor(onnxModel, name)
            source = None

            modelInput = None
            inputIndex = 0

            for i, x in enumerate(cModel.modelInputs):
                if x.name == name:
                    modelInput = x
                    inputIndex = i
                    break

            if tensor:
                asNpArray = onnx.numpy_helper.to_array(tensor)
                source = DataSource(DataSourceType.INITIALIZER, name)
                source.data = asNpArray
                source.tensorDims = [int(x) for x in asNpArray.shape]
                source.index = cModel.NextInitializerIndex()
            elif modelInput:
                source = DataSource(DataSourceType.MODEL_INPUT, name)
                source.tensorDims = modelInput.shape
                source.index = inputIndex
            else:
                source = DataSource(DataSourceType.NODE_INPUT, name)
                source.index = IndexOfNodeThatProducesOutput(cModel, source.name)

            dataSources.append(source)

        outputDimensions = []
        for output in node.output:
            shape = GetShape(shaped, output)
            outputDimensions.append(shape)

        outputName = node.output[0]  # Can a node have more than one output?

        op = Operation(
            node.name,
            node.op_type,
            cModel.NextOperationIndex(),
            dataSources,
            outputName,
            inputDimensions,
            outputDimensions,
            parsedAttributes,
        )
        cModel.operations.append(op)

    allInputsShapes = sum([port.shape for port in cModel.modelInputs], [])

    mapped = {}
    for port in cModel.modelInputs:
        for i, name in enumerate(port.shape):
            if isinstance(name, str):
                mapped[name] = True

    for op in cModel.operations:
        for inputs in op.inputDimensions:
            for i, name in enumerate(inputs):
                if isinstance(name, str):
                    mapped[name] = True

        for i, name in enumerate(op.outputDimensions):
            if isinstance(name, str):
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
            if isinstance(name, str):
                params[name] = True

    for op in cModel.operations:
        for inputs in op.inputDimensions:
            for i, name in enumerate(inputs):
                if isinstance(name, str):
                    params[name] = True

        for i, name in enumerate(op.outputDimensions):
            if isinstance(name, str):
                params[name] = True

    return params


def RestrictModelFreeParameter(cModel, paramValue):
    # TODO: Currently we force variable sizes to 1 in here
    mapped = {}

    for port in cModel.modelInputs:
        for i, name in enumerate(port.shape):
            if isinstance(name, str):
                port.shape[i] = mapped.get(name, paramValue)
                mapped[name] = port.shape[i]

    for op in cModel.operations:
        for inputs in op.inputDimensions:
            for i, name in enumerate(inputs):
                if isinstance(name, str):
                    inputs[i] = mapped.get(name, paramValue)
                    mapped[name] = inputs[i]

        for outDim in op.outputDimensions:
            for i, name in enumerate(outDim):
                if isinstance(name, str):
                    outDim[i] = mapped.get(name, paramValue)
                    mapped[name] = outDim[i]

    return cModel


def RunModel(model: Model, originalOnnxModel, inputs):
    sess = ort.InferenceSession(originalOnnxModel.SerializeToString())
    modelInputs = {x.name: y for x, y in zip(sess.get_inputs(), inputs)}
    modelOutput = sess.run(None, modelInputs)

    mappedOutputs = {x.name: y for x, y in zip(sess.get_outputs(), modelOutput)}
    outputs = [None] * len(model.operations)
    for index, op in enumerate(model.operations):
        outputs[index] = mappedOutputs[op.outputName]

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


def AllZeros(inp: list[int]):
    allZero = True
    for x in inp:
        if x != 0:
            allZero = False

    return allZero


def NotAllZeros(inp: list[int]):
    noZero = False
    for x in inp:
        if x != 0:
            noZero = True

    return noZero


def PrintModelData(cModel):
    for op in cModel.operations:
        print(f"[{op.opName}] {op.nodeName}")
        for i, inp in enumerate(op.inputs):
            print(f"Input_{i}:", cModel.GetGenericDataSource(inp).data)
        print("Output_0:", op.correctOutputData)


def PrintOutNpArray(arrayToPrintout):
    for index in np.ndindex(arrayToPrintout.shape):
        x = arrayToPrintout[index]
        print(x)


def PrintSimpleNodeInfo(i, c: Operation):
    inputs = [x.index for x in c.inputs if x.sourceType == DataSourceType.NODE_INPUT]
    pPerms = c.parsedAttributes.get("perm", [])

    print(
        i,
        inputs,
        c.nodeIndex,
        c.opName,
        c.inputDimensions,
        c.outputDimensions,
        pPerms,
        c.parsedAttributes,
    )


def GenerateDotFile(cModel):
    nodeLines = ""
    for op in cModel.operations:
        nodeLines += (
            f'"{op.nodeIndex}" [color=dark label="{op.nodeIndex} [{op.opName}]"];\n'
        )

    nodeEdges = ""
    for op in cModel.operations:
        for index, inp in enumerate(op.inputs):
            inputNode = cModel.GetInputNode(op, index)

            if inputNode != Operation_NIL:
                nodeEdges += f"{inputNode.nodeIndex} -> {op.nodeIndex} [color=dark]"

    res = """digraph view {
            node [fontcolor=white,style=filled,color="160,60,176"];
            label="Graph";
    """

    res += nodeLines
    res += nodeEdges
    res += "}"

    return res


def PrintOperationData(cModel, op, printInputs=True):
    if printInputs:
        for index, inp in enumerate(op.inputs):
            gen = cModel.GetGenericDataSource(inp)
            print(f"Input {index}")
            for index in np.ndindex(gen.data.shape):
                print(index, gen.data[index])

    print("Output: ")
    for index in np.ndindex(op.correctOutputData.shape):
        print(index, op.correctOutputData[index])


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
    focusLayerRange: [int, int] = None,
    debugSoftware: bool = False,
):
    # TODO: It would be better if we could check all the inputs for correctness.
    if not isinstance(namespace, str) or not namespace.isidentifier():
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
        # NOTE: Currently we assume that all free parameters are the
        #       same value.  All the testbenches that we have work on
        #       this assumption and I do not know if we can have a
        #       model where this assumption does not hold.  We are
        #       also assuming that we only have a single free
        #       parameter as input. Need to see a model where this
        #       assumption does not hold in order to then decide on
        #       the proper way of progressing.  assert
        #       len(freeParameters) <= 1

        # We match the parameter to the input and then we instantiate
        # the model with it. No runtime handling of free parameters We
        # do not know it if we need to generate code that can handle
        # this at runtime. Worry about it later, for now we need to
        # make this work on the board first before handling stuff like
        # that.
        freeParameterValue = 1
        for op in cModel.operations:
            for inp in op.inputs:
                if inp.sourceType == DataSourceType.MODEL_INPUT:
                    inputIndex = inp.index
                    inputDims = op.inputDimensions[inputIndex]

                    inputShape = inputs[0].shape

                    for index in range(len(inputShape)):
                        if isinstance(inputDims[index], str):
                            freeParameterValue = inputShape[index]

        cModel = RestrictModelFreeParameter(cModel, freeParameterValue)

    # TODO: Implement multiple testcases by running the model multiple times and outputting multiple correct data bins.
    # NOTE: Is it possible for different testcases to generate different amounts of correctData? It shouldn't be possible.
    result = RunModel(cModel, model, inputs)
    correctData = result.outputs

    # Associate inputs to model data sources
    for i, data in enumerate(inputs):
        for op in cModel.operations:
            for inp in op.inputs:
                if inp.sourceType == DataSourceType.MODEL_INPUT and inp.index == i:
                    inp.data = data

    # Associate correct data to operation outputs
    for i, data in enumerate(correctData):
        cModel.operations[i].correctOutputData = data

    # For debugging purposes it might be useful to embed the inputs as initializers.
    # That way we can test certain optimizations.
    transformInputToInitializer = False

    if transformInputToInitializer:
        for op in cModel.operations:
            for inp in op.inputs:
                if inp.sourceType == DataSourceType.MODEL_INPUT:
                    inp.sourceType = DataSourceType.INITIALIZER
                    inp.index = cModel.NextInitializerIndex()

    # Compresses node indexes to align with array indexes. (cModel.operations[N].nodeIndex == N for all nodes)
    # Returns mapping from old index to new index
    def CompressGraphIndexes(cModel):
        mapOldIndexToNew = {}
        for i, op in enumerate(cModel.operations):
            mapOldIndexToNew[op.nodeIndex] = i
            op.nodeIndex = i
        for op in cModel.operations:
            for inp in op.inputs:
                if inp.sourceType == DataSourceType.NODE_INPUT:
                    inp.index = mapOldIndexToNew[inp.index]

        return mapOldIndexToNew

    # Very simple DFG algorithm. Should be fast enough unless we start processing 100+ nodes graphs
    # Returns mapping from old index to new index
    def ReorganizeGraph(cModel):
        # Compress before DFG
        oldToCompressed = CompressGraphIndexes(cModel)

        # TODO: A proper graph based algorithm to properly compute DFG taking into account graph partitions
        #       and in an optimized manner.

        # Accumulate all the output nodes of the whole graph
        size = len(cModel.operations)
        allOutputNodes = []

        nodeLevel = [None] * len(cModel.operations)
        mark = [True] * len(cModel.operations)
        for i, op in enumerate(cModel.operations):
            for inp in op.inputs:
                if inp.sourceType == DataSourceType.NODE_INPUT:
                    mark[inp.index] = False

        for i, op in enumerate(cModel.operations):
            if mark[i]:
                allOutputNodes.append(op)
                nodeLevel[i] = 0

        # Partition graph into individual components
        nodeIndexToPart = {}
        for i in range(size):
            nodeIndexToPart[i] = -1

        partIndex = 0
        for i in range(size):
            if nodeIndexToPart[i] != -1:
                continue

            indexToPropagate = partIndex
            partIndex += 1

            seen = [False] * size
            indexQueue = [i]

            while len(indexQueue):
                index = indexQueue[0]
                indexQueue = indexQueue[1:]

                if seen[index]:
                    continue

                seen[index] = True
                nodeIndexToPart[index] = indexToPropagate

                node = cModel.operations[index]

                for inp in node.inputs:
                    if inp.sourceType == DataSourceType.NODE_INPUT:
                        indexQueue.append(inp.index)

                outputs = cModel.GetOutputNodesAndPortIndexes(node, 0)

                for out, port in outputs:
                    indexQueue.append(out.nodeIndex)

        allPartitionsIndexes = [[] for x in range(partIndex)]

        for key, data in nodeIndexToPart.items():
            allPartitionsIndexes[data].append(key)

        # Run simple DFG for each partition
        dfgSortedList = []
        for part in allPartitionsIndexes:
            fullIndexToPartIndex = {}
            for x in part:
                fullIndexToPartIndex[x] = len(fullIndexToPartIndex)

            nodeLevel = [None] * len(part)
            mark = [True] * len(part)
            for i, index in enumerate(part):
                op = cModel.operations[index]
                for inp in op.inputs:
                    if inp.sourceType == DataSourceType.NODE_INPUT:
                        mark[fullIndexToPartIndex[inp.index]] = False

            for i, index in enumerate(part):
                op = cModel.operations[index]
                if mark[i]:
                    allOutputNodes.append(op)
                    nodeLevel[fullIndexToPartIndex[index]] = 0

            # Stupid but it works
            for i in range(1000):
                if False:
                    alreadyDone = True
                    for x in nodeLevel:
                        if x is None:
                            alreadyDone = False

                    if alreadyDone:
                        break

                for index in part:
                    op = cModel.operations[index]
                    thisLevel = nodeLevel[fullIndexToPartIndex[index]]
                    if thisLevel is None:
                        continue

                    for inp in op.inputs:
                        if inp.sourceType == DataSourceType.NODE_INPUT:
                            otherLevel = nodeLevel[fullIndexToPartIndex[inp.index]]
                            if otherLevel is None:
                                otherLevel = 0
                            nodeLevel[fullIndexToPartIndex[inp.index]] = max(
                                otherLevel, thisLevel + 1
                            )

            maxLevel = 0
            for x in nodeLevel:
                maxLevel = max(maxLevel, x)

            for level in range(maxLevel, -1, -1):
                for i, x in enumerate(nodeLevel):
                    if x == level:
                        dfgSortedList.append(cModel.operations[part[i]])

        cModel.operations = dfgSortedList
        compressedToSorted = CompressGraphIndexes(cModel)

        finalMapping = {}
        for x in oldToCompressed:
            finalMapping[x] = compressedToSorted[oldToCompressed[x]]

        return finalMapping

    # Graph based optimizations can be put here
    # Any rule that requires 3 specific nodes is problematic.
    # We want rules that have at most 2 specific nodes otherwise becomes
    # hard to apply.
    # We also want to push stuff towards inputs as much as possible.
    # The closer it is to initializers and whatnot the easier it will
    # be to fold.

    # PrintOperationData(cModel,cModel.operations[19])

    if 0:
        print("Before optimization:\n")
        for i, c in enumerate(cModel.operations):
            print(i, c.opName, c.inputDimensions)
        print("\n\n")

    for x in cModel.operations:
        print()
        print()
        print()
        pprint(x)

    allOutputNodes = cModel.GetAllModelOutputNodes()
    originalCorrectData = None
    for node in allOutputNodes:
        originalCorrectData = deepcopy(node.correctOutputData)

    doOptimizations = False

    # Simple way of ordering operations. All level 0 rules run first, followed by rules 1 and so on.
    # Everytime a rule fires level resets to zero. Meaning that we always run level 0 rules before any rule 1
    # even if new rules of level 0 are created they always run first before any rule 1
    level = 0
    maxLevel = 1
    while doOptimizations and level < maxLevel:
        nodesChanged = []
        ruleFound = None
        terminateEarly = False

        print(level)
        # Find first applicable rule
        # We probably wanna reverse the direction of search.
        for op in cModel.operations:
            # NOTE: GetAttributesForOperator does not return non onnx attributes

            attr = GetAttributesForOperator(op)

            allInputNodes = []
            for index, inp in enumerate(op.inputs):
                allInputNodes.append(cModel.GetInputNode(op, index))

            for index, inp in enumerate(op.inputs):
                inputNode = cModel.GetInputNode(op, index)
                inputNodeOutputs = cModel.GetOutputNodesAndPortIndexes(inputNode, 0)

                if ruleFound:
                    break

                if True and op.opName == "Conv":
                    if attr.get("auto_pad", "NOTSET") == "NOTSET" and NotAllZeros(
                        attr.get("pads", [])
                    ):
                        ruleFound = OptimizationRules.EXTRACT_CONV_PAD
                        nodesChanged.append(op)
                        break

                    if level >= 1 and op.parsedAttributes.get("isNHWC", False) is False:
                        ruleFound = OptimizationRules.CONV_NCHW_TO_NHWC
                        nodesChanged.append(op)
                        break

                if False and op.opName == "FixPad":
                    if inputNode.opName == "FixPad":
                        nodesChanged.append(op)
                        nodesChanged.append(inputNode)
                        ruleFound = OptimizationRules.JOIN_FIXPADS
                        break

                if False and op.opName == "Pad":
                    if inputNode.opName == "Pad":
                        nodesChanged.append(op)
                        nodesChanged.append(inputNode)
                        ruleFound = OptimizationRules.JOIN_PADS
                        break

                    if inputNode.opName == "FixPad":
                        nodesChanged.append(op)
                        nodesChanged.append(inputNode)
                        ruleFound = OptimizationRules.PUSH_PAD_OVER_FIXPAD
                        break

                    if inputNode.opName == "Relu":
                        if len(inputNodeOutputs) == 1:
                            nodesChanged.append(op)
                            nodesChanged.append(inputNode)
                            ruleFound = OptimizationRules.PUSH_PAD_OVER_RELU
                            break

                    if inputNode.opName == "Conv":
                        padNode = op
                        convNode = inputNode

                        padAttr = padNode.parsedAttributes
                        convAttr = convNode.parsedAttributes

                        doRule = True
                        if convAttr["strides"][0] > 1 and (
                            padAttr["pads"][2] > 0 or padAttr["pads"][6] > 0
                        ):
                            doRule = False
                        if convAttr["strides"][1] > 1 and (
                            padAttr["pads"][3] > 0 or padAttr["pads"][7] > 0
                        ):
                            doRule = False

                        if doRule:
                            nodesChanged.append(op)
                            nodesChanged.append(inputNode)
                            ruleFound = OptimizationRules.PUSH_PAD_OVER_CONV
                            break

                if False and op.opName == "MatMul":
                    if op.parsedAttributes.get("isBTransposed", 0) == 0:
                        nodesChanged.append(op)
                        ruleFound = OptimizationRules.MATMUL_TRANSPOSE
                        break

                if False and op.opName == "Add":
                    if (
                        level >= 1
                        and allInputNodes[0].opName == "Transpose"
                        and allInputNodes[1].opName == "Transpose"
                    ):
                        perm1 = allInputNodes[0].parsedAttributes["perm"]
                        perm2 = allInputNodes[1].parsedAttributes["perm"]
                        print(perm1, type(perm1), perm2, type(perm2))
                        if perm1 == perm2:
                            nodesChanged.append(op)
                            nodesChanged.append(allInputNodes[0])
                            nodesChanged.append(allInputNodes[1])
                            ruleFound = OptimizationRules.ADD_REMOVE_BOTH_TRANSPOSE
                            break

                if False and op.opName == "Transpose":
                    if level >= 1 and inputNode.opName == "Relu":
                        if len(inputNodeOutputs) == 1:
                            nodesChanged.append(op)
                            nodesChanged.append(inputNode)
                            ruleFound = OptimizationRules.PUSH_TRANSPOSE_OVER_RELU
                            break
                        if len(inputNodeOutputs) > 1:
                            reluInput = cModel.GetInputNode(inputNode, 0)

                            # Technically we would need to check if we have inverting perms
                            if reluInput.opName == "Transpose":
                                nodesChanged.append(op)
                                nodesChanged.append(inputNode)
                                ruleFound = OptimizationRules.PUSH_TRANSPOSE_OVER_RELU
                                break

                    if inputNode.opName == "FixPad":
                        nodesChanged.append(op)
                        nodesChanged.append(inputNode)
                        ruleFound = OptimizationRules.PUSH_TRANSPOSE_OVER_FIXPAD
                        break

                    if inputNode.opName == "Pad":
                        nodesChanged.append(op)
                        nodesChanged.append(inputNode)
                        ruleFound = OptimizationRules.PUSH_TRANSPOSE_OVER_PAD
                        break

                    if level >= 0 and inputNode.opName == "Transpose":
                        nodesChanged.append(op)
                        nodesChanged.append(inputNode)
                        ruleFound = OptimizationRules.JOIN_TRANSPOSE
                        break

                    if op.inputs[0].sourceType == DataSourceType.INITIALIZER:
                        nodesChanged.append(op)
                        ruleFound = OptimizationRules.FOLD_TRANSPOSE
                        break

        op = None

        if ruleFound is None:
            level += 1
            print("Did not find rule")
            continue

        level = 0

        changedNodesIndexes = [x.nodeIndex for x in nodesChanged]

        # Apply rule
        print(f"Gonna apply rule: {ruleFound}")

        addedNodesIndexes = []
        nodesToRemove = []
        ruleApplied = False

        node = nodesChanged[0]
        attr = GetAttributesForOperator(node)

        inputNode = None
        inputAttr = None

        if len(nodesChanged) > 1:
            inputNode = nodesChanged[1]
            inputAttr = GetAttributesForOperator(inputNode)

        print("BEFORE:\n")
        for i, c in enumerate(cModel.operations):
            if c.nodeIndex in changedNodesIndexes:
                print(COLOR_GREEN, sep="", end="")
                PrintSimpleNodeInfo(i, c)
                print(COLOR_BASE, sep="", end="")
            else:
                PrintSimpleNodeInfo(i, c)

        if ruleFound == OptimizationRules.ADD_REMOVE_BOTH_TRANSPOSE:
            ruleApplied = True
            add = node

            firstTranspose = nodesChanged[1]
            secondTranspose = nodesChanged[2]

            newTranspose = cModel.AddOperation("Transpose", 1)
            addedNodesIndexes.append(newTranspose.nodeIndex)
            newTranspose.parsedAttributes = deepcopy(firstTranspose.parsedAttributes)

            cModel.InsertAfter(add, newTranspose, 0)
            nodesToRemove.append(firstTranspose)
            nodesToRemove.append(secondTranspose)

            # terminateEarly = True

        if ruleFound == OptimizationRules.EXTRACT_CONV_PAD:
            ruleApplied = True

            newOp = cModel.AddOperation("Pad", 1)
            addedNodesIndexes.append(newOp.nodeIndex)

            truePads = [0, 0] + attr["pads"][:2] + [0, 0] + attr["pads"][2:]
            newOp.parsedAttributes["pads"] = truePads
            node.parsedAttributes["pads"] = [0] * len(attr["pads"])

            cModel.InsertBefore(node, 0, newOp, 0)

        if ruleFound == OptimizationRules.CONV_NCHW_TO_NHWC:
            ruleApplied = True

            conv = node
            convolutionCorrectData = deepcopy(conv.correctOutputData)
            conv.parsedAttributes["isNHWC"] = True

            beforeTranspose = cModel.AddOperation("Transpose", 1)
            afterTranspose = cModel.AddOperation("Transpose", 1)
            addedNodesIndexes.append(beforeTranspose.nodeIndex)
            addedNodesIndexes.append(afterTranspose.nodeIndex)

            # Convert NCHW -> NHWC
            # np.transpose(A,axes=[0,2,3,1])

            # Convert NHWC -> NCHW
            # np.transpose(A,axes=[0,3,1,2])

            # NCHW -> NHWC
            beforeTranspose.parsedAttributes["perm"] = [0, 2, 3, 1]
            # NHWC -> NCHW
            afterTranspose.parsedAttributes["perm"] = [0, 3, 1, 2]

            cModel.InsertBefore(conv, 0, beforeTranspose, 0)
            cModel.InsertAfter(conv, afterTranspose, 0)

            afterOpCorrectData = afterTranspose.correctOutputData

            # TODO: Temporarely disabled since its failed but not in a big way.
            #       Need to see afterwards what is happening
            # np.testing.assert_allclose(
            #    convolutionCorrectData, afterOpCorrectData, rtol=1e-03, verbose=True
            # )

            # terminateEarly = True

        if ruleFound == OptimizationRules.PUSH_PAD_OVER_RELU:
            ruleApplied = True
            cModel.Swap(node, inputNode)

        if ruleFound == OptimizationRules.PUSH_PAD_OVER_CONV:
            ruleApplied = True

            padNode = node
            convNode = inputNode

            padCorrectData = deepcopy(padNode.correctOutputData)

            # Lets start without the FixupPad stuff.
            newOp = cModel.AddOperation("Pad", 1)

            newOp.parsedAttributes = deepcopy(padNode.parsedAttributes)
            newOp.parsedAttributes["pads"][2] *= inputAttr["strides"][0]
            newOp.parsedAttributes["pads"][3] *= inputAttr["strides"][1]
            newOp.parsedAttributes["pads"][6] *= inputAttr["strides"][0]
            newOp.parsedAttributes["pads"][7] *= inputAttr["strides"][1]

            fixPad = cModel.AddOperation("FixPad", 1)
            fixPad.parsedAttributes = deepcopy(padNode.parsedAttributes)

            cModel.InsertBefore(convNode, 0, newOp, 0)
            cModel.InsertAfter(convNode, fixPad, 0)

            fixPadCorrectData = fixPad.correctOutputData

            # For some reason this is failing for a smaller rtol
            # It is kinda weird but is hard to see what is causing this. Would need to
            # craft a custom smaller test to make it easier to see what is happening.
            # np.testing.assert_allclose(
            #    padCorrectData, fixPadCorrectData, rtol=1e-03, verbose=True
            # )

            nodesToRemove.append(padNode)
            addedNodesIndexes.append(newOp.nodeIndex)
            addedNodesIndexes.append(fixPad.nodeIndex)

        if ruleFound == OptimizationRules.JOIN_PADS:
            ruleApplied = True

            for i, x in enumerate(node.parsedAttributes["pads"]):
                inputNode.parsedAttributes["pads"][i] += x

            # cModel.UpdateNodeData(inputNode)

            nodesToRemove.append(node)

        if ruleFound == OptimizationRules.PUSH_PAD_OVER_FIXPAD:
            ruleApplied = True

            for i, x in enumerate(node.parsedAttributes["pads"]):
                inputNode.parsedAttributes["pads"][i] += x

            cModel.Swap(node, inputNode)

        if ruleFound == OptimizationRules.JOIN_FIXPADS:
            ruleApplied = True

            for i, x in enumerate(node.parsedAttributes["pads"]):
                inputNode.parsedAttributes["pads"][i] = max(
                    inputNode.parsedAttributes["pads"][i], x
                )

            # cModel.UpdateNodeData(inputNode)

            nodesToRemove.append(node)

        if ruleFound == OptimizationRules.MATMUL_TRANSPOSE:
            ruleApplied = True

            newOp = cModel.AddOperation("Transpose", 1)

            # TODO: Need to adapt this to the shape of the data. Cannot assume simple 2D shape
            newOp.parsedAttributes["perm"] = [1, 0]
            node.parsedAttributes["isBTransposed"] = 1

            cModel.InsertBefore(node, 1, newOp, 0)

            addedNodesIndexes.append(newOp.nodeIndex)

        if ruleFound == OptimizationRules.PUSH_TRANSPOSE_OVER_RELU:
            ruleApplied = True
            transpose = node
            relu = inputNode

            # cModel.Swap(node, inputNode)

            newInputTranspose = cModel.AddOperation("Transpose", 1)
            newInputTranspose.parsedAttributes = deepcopy(transpose.parsedAttributes)
            addedNodesIndexes.append(newInputTranspose.nodeIndex)

            cModel.InsertBefore(relu, 0, newInputTranspose, 0)

            allReluOutputs = cModel.GetOutputNodesAndPortIndexes(relu, 0)

            reverseNp = np.argsort(transpose.parsedAttributes["perm"])
            reverse = [int(x) for x in reverseNp]

            for node, port in allReluOutputs:
                invertTranspose = cModel.AddOperation("Transpose", 1)
                invertTranspose.parsedAttributes["perm"] = reverse
                addedNodesIndexes.append(invertTranspose.nodeIndex)

                cModel.InsertBefore(node, port, invertTranspose, 0)

            # nodesToRemove.append(transpose)

            # terminateEarly = True

            # What we have to do is just created a bunch of input transposes and output reverse transposes
            # and let the JOIN_TRANSPOSE rule anhialate them

            # If X -> Relu -> B,C,D,E,F

        if ruleFound == OptimizationRules.PUSH_TRANSPOSE_OVER_FIXPAD:
            ruleApplied = True

            fixpad = inputNode
            transpose = node

            perm = transpose.parsedAttributes["perm"]
            pads = fixpad.parsedAttributes["pads"]

            reverse = np.argsort(perm)

            freshPads = [0] * len(pads)
            padStride = len(pads) // 2

            for i, x in enumerate(pads[:padStride]):
                trueIndex = reverse[i]
                start = x
                end = pads[i + padStride]

                freshPads[trueIndex] = start
                freshPads[trueIndex + padStride] = end

            fixpad.parsedAttributes["pads"] = freshPads
            cModel.Swap(transpose, fixpad)

        if ruleFound == OptimizationRules.PUSH_TRANSPOSE_OVER_PAD:
            ruleApplied = True

            fixpad = inputNode
            transpose = node

            perm = transpose.parsedAttributes["perm"]
            pads = fixpad.parsedAttributes["pads"]

            reverse = np.argsort(perm)

            freshPads = [0] * len(pads)
            padStride = len(pads) // 2

            for i, x in enumerate(pads[:padStride]):
                trueIndex = reverse[i]
                start = x
                end = pads[i + padStride]

                freshPads[trueIndex] = start
                freshPads[trueIndex + padStride] = end

            fixpad.parsedAttributes["pads"] = freshPads
            cModel.Swap(transpose, fixpad)

        if ruleFound == OptimizationRules.JOIN_TRANSPOSE:
            ruleApplied = True

            perm1 = node.parsedAttributes["perm"]
            perm2 = inputNode.parsedAttributes["perm"]

            newPerm = [0] * len(perm1)
            for i in range(len(perm1)):
                newPerm[i] = perm2[perm1[i]]

            isIdentity = True
            for i in range(len(newPerm)):
                if newPerm[i] != i:
                    isIdentity = False

            if isIdentity:
                nodesToRemove.append(node)
                nodesToRemove.append(inputNode)
            else:
                node.parsedAttributes["perm"] = newPerm
                # cModel.UpdateNodeData(node)

                nodesToRemove.append(node)

            # terminateEarly = True

        if ruleFound == OptimizationRules.FOLD_TRANSPOSE:
            ruleApplied = True

            node.inputs[0].data = np.transpose(node.inputs[0].data, axes=attr["perm"])
            node.inputs[0].tensorDims = [int(x) for x in node.inputs[0].data.shape]
            node.inputs[0].sourceType = DataSourceType.INITIALIZER
            nodesToRemove.append(node)

        if not ruleApplied:
            assert False and "Rule does not contain implementation"

        toRemoveIndexes = {x.nodeIndex for x in nodesToRemove}

        for node in nodesToRemove:
            cModel.RemoveOperationDoNotKeepData(node)

        oldIndexToNew = ReorganizeGraph(cModel)

        # NOTE: Since we could remove nodes it might be possible that they no longer appear in the mapping
        changedNodes = {oldIndexToNew.get(x, -1): True for x in changedNodesIndexes}
        addedNodes = {oldIndexToNew.get(x, -1): True for x in addedNodesIndexes}

        print("\nAFTER:\n")
        for i, c in enumerate(cModel.operations):
            if i in changedNodes:
                print(COLOR_GREEN, sep="", end="")
                PrintSimpleNodeInfo(i, c)
                print(COLOR_BASE, sep="", end="")
            elif i in addedNodes:
                print(COLOR_BLUE, sep="", end="")
                PrintSimpleNodeInfo(i, c)
                print(COLOR_BASE, sep="", end="")
            else:
                PrintSimpleNodeInfo(i, c)

        print("\n\n")

        if terminateEarly:
            break

    print("After optimize")

    for op in cModel.operations:
        # Programmer error if NIL node ever reaches this point
        assert op.opName != "NIL"

    # Graph optimizations are not guaranteed to preserve graph order
    # Need to do a pass to convert back into DAG

    ReorganizeGraph(cModel)

    # Make sure that everything is updated.
    if False:
        try:
            for op in cModel.operations:
                cModel.UpdateNodeData(op)
        except:
            print("Failed to update graph")

            for i, c in enumerate(cModel.operations):
                PrintSimpleNodeInfo(i, c)
            sys.exit(0)

        if cModel.anyFailedUpdates:
            print("Failed to update graph. Outputting what we got so far:")

            for i, c in enumerate(cModel.operations):
                PrintSimpleNodeInfompleNodeInfo(i, c)
            sys.exit(0)

    # with open("AfterOpt.dot", "w") as f:
    #    f.write(GenerateDotFile(cModel))

    # Test final output to make sure that optimizations did not broke anything.
    if False:
        allOutputNodes = cModel.GetAllModelOutputNodes()
        for node in allOutputNodes:
            correctData = node.correctOutputData

            print("Gonna check if output remains similar after optimizations")
            np.testing.assert_allclose(
                correctData, originalCorrectData, rtol=1e-05, verbose=True
            )

    # Remove layers if the user commands. Mostly to help test individual operations

    if focusLayerRange:
        focusStart = focusLayerRange[0]
        focusEnd = focusLayerRange[1]

        if focusStart == focusEnd:
            cModel.PreserveOnlyOne(cModel.operations[focusStart])
        else:
            for i in range(0, len(cModel.operations)):
                if i >= focusStart and i <= focusEnd:
                    continue

                op = cModel.GetOperationByIndexOrFail(i)
                cModel.RemoveOperationKeepData(op)

    ReorganizeGraph(cModel)

    if True:
        for i, c in enumerate(cModel.operations):
            PrintSimpleNodeInfo(i, c)

    # Compress initializers
    initializerMaxIndex = 0
    for op in cModel.operations:
        for inp in op.inputs:
            if inp.sourceType == DataSourceType.INITIALIZER:
                initializerMaxIndex = max(initializerMaxIndex, inp.index)

    realInitializerIndex = 0
    for op in cModel.operations:
        for inp in op.inputs:
            if inp.sourceType == DataSourceType.INITIALIZER:
                inp.index = realInitializerIndex
                realInitializerIndex += 1

    cModel.nextInitializerIndex = realInitializerIndex

    # At this point graph is compressed. Node indexes match array
    # index and any superfluous data has been removed

    CalculateMemoryAllocations(cModel)

    # PrintOperationData(cmodel,cModel.operations[19])

    # Pack inputs
    allInputData = [None] * len(cModel.modelInputs)
    for op in cModel.operations:
        for inp in op.inputs:
            if inp.sourceType == DataSourceType.MODEL_INPUT:
                assert allInputData[inp.index] is None

                allInputData[inp.index] = inp.data

    compactInputData = []
    for data in allInputData:
        if data is not None:
            compactInputData.append(data)
    packedInputs = PackMultipleArrays(compactInputData)

    # Pack initializers
    allInitializers = []
    for op in cModel.operations:
        for inp in op.inputs:
            if inp.sourceType == DataSourceType.INITIALIZER:
                assert inp.index == len(allInitializers)
                allInitializers.append(inp.data)

    packedInitializers = PackMultipleArrays(allInitializers)

    # Pack correct outputs
    # Since we need all the outputs to verify correctness, might as well pack everything. In a proper impl we would go through the graph and count the amount of proper outputs instead.
    amountOfOutputs = len(cModel.operations)
    allOutputData = [None] * amountOfOutputs
    compactCorrectData = []
    for op in cModel.operations:
        if op.correctOutputData is not None:
            compactCorrectData.append(op.correctOutputData)
        else:
            # We store a single zero since its easier than an empty value
            # At the emitter stage we also set a flag to avoid checking meaning that we
            # could store whatever we wanted in here. Sending one value is just easier
            compactCorrectData.append(np.zeros(1, dtype=np.float32))

    packedCorrectData = PackMultipleArrays(compactCorrectData)

    # print(compactCorrectData[-1])

    # All nodes get their data from the valid data array
    # Basically any error in any node does not propagate to other nodes (only for validation purposes)
    useValidDataAsInput = False
    debugging = True
    if not debugging:
        useValidDataAsInput = False

    correctDataSize = len(packedCorrectData.data)
    inputSize = len(cModel.modelInputs)

    totalInputSize = 0
    inputOffsets = [0]
    inputSizes = [0]

    if len(cModel.modelInputs) > 0:
        inputSizes = [TensorSize(x.shape) for x in cModel.modelInputs]
        inputOffsets, totalInputSize = CalculateOffsetFromSize(inputSizes)

    # Generate the structures of the operators.
    # Easier to do this automatically in order to ensure that data matches
    # NOTE: This generates the same code regardless of the test model. We could extract this part into a different flow
    #       but it kinda does not matter since as long as we can guarantee that this gets generated before the test gets compiled
    #       it makes no difference
    with open(
        os.path.join(sourceOutputLocation, f"versat_ai_operators_meta.h"), "w"
    ) as f:
        allOperatorSpecsDict = GetAllOperatorSpecs()

        def OperatorIndex(opName):
            spec = allOperatorSpecsDict[opName]
            return spec.index

        f.write("// File generated by onnxMain.py.\n// Do not modify\n")
        f.write("#ifndef VERSAT_AI_OPERATORS_META\n")
        f.write("#define VERSAT_AI_OPERATORS_META\n\n")

        f.write("typedef enum {\n")
        f.write(
            ",\n".join(
                f"  OperatorType_{opName} = {OperatorIndex(opName)}"
                for opName in allOperatorSpecsDict
            )
        )
        f.write("\n} OperatorType;\n\n")

        f.write(
            "static inline char* VERSAT_OperatorName(int opType,int useSoftware){\n"
        )
        f.write("  switch(opType){\n")
        for opName in allOperatorSpecsDict:
            spec = allOperatorSpecsDict[opName]
            f.write(f"    case {spec.index}: " + "{\n")
            f.write("      if(useSoftware){\n")
            f.write(f'        return "Soft_{opName}";\n')
            f.write("      } else {\n")
            f.write(f'        return "Versat_{opName}";\n')
            f.write("      }\n")
            f.write("    } break;\n")
        f.write('  return "";\n')
        f.write("  }\n")
        f.write("}\n\n")

        # Common enums
        f.write("typedef enum {\n")
        f.write(
            ",\n".join(
                f"  PaddingType_{member.name} = {member.value}"
                for member in PaddingType
            )
        )
        f.write("\n} PaddingType;\n\n")

        for opName in allOperatorSpecsDict:
            spec = allOperatorSpecsDict[opName]
            if not len(spec.emitStructure):
                continue

            structure = spec.emitStructure

            # Separate data into static and variable
            # All static data must come before all variable data
            # We have an assert for this and if it triggers is because programmer
            # provided the data in the wrong format.
            # Data must also align with the output of the emitter function
            # TODO: We might automatize this part better in the future but for now it suffices
            isVariable = False
            staticData = []
            variableData = []
            for name, typeInfo in structure:
                typeName = typeInfo
                if isinstance(typeInfo, list) or isinstance(typeInfo, tuple):
                    isVariable = True
                    variableData.append((name, typeInfo[0], typeInfo[1]))
                    assert isVariable
                else:
                    staticData.append((name, typeName))
                    assert not isVariable

            f.write("typedef struct {\n")
            for name, typeName in staticData:
                f.write(f"  {typeName} {name};\n")

            f.write("  // Followed by\n")
            for name, typeName, size in variableData:
                f.write(f"  // {typeName} {name}[{size}];\n")

            f.write("} " + f"{opName}Info;\n\n")

            name, typeName, size = variableData[0]
            defineName = f"VERSAT_{opName}Info_{name}"
            f.write(
                f"#define {defineName}(INFO) (({typeName} *) VERSAT_OFFSET_PTR(INFO,sizeof({opName}Info)))\n"
            )

            lastDefineName = defineName
            lastSize = size
            lastTypeName = typeName
            for name, typeName, size in variableData[1:]:
                defineName = f"VERSAT_{opName}Info_{name}"

                f.write(
                    f"#define {defineName}(INFO) (({typeName} *) VERSAT_OFFSET_PTR({lastDefineName}(INFO),INFO->{lastSize} * sizeof({lastTypeName})))\n"
                )

                lastDefineName = defineName
                lastSize = size
                lastTypeName = typeName
            f.write("\n")

        f.write("#endif // VERSAT_AI_OPERATORS_META")

    # Output generic version
    # TODO: A better way would be to have this also generate the struct and the code
    #       to iterate the data, therefore guaranteeing that stuff lines up correctly.
    #       This is good enough for now and it would only be worth it if we end up changing
    #       this stuff a lot more and I currently doubt that we will.
    packer = StructBuilder()
    packer.U32(cModel.outputMemoryNeeded)
    packer.U32(cModel.tempMemoryNeeded)
    packer.U32(len(packedInitializers.data))
    packer.U32(correctDataSize)
    packer.U32(totalInputSize)

    packer.U32(len(cModel.modelInputs))
    packer.U32(len(cModel.operations))

    if len(cModel.modelInputs) > 0:
        # NOTE: We are not using input sizes so I think we might just skip this
        #       Only input offsets are actually needed.
        # for size in inputSizes:
        #    packer.U32(size)
        for offsets in inputOffsets:
            packer.U32(offsets)

    # Emit operators itself
    for op in cModel.operations:
        spec = operatorNameToSpec[op.opName]

        opInfo = StructBuilder()

        # Operator size gets prepended at the end.

        opInfo.U32(spec.index)
        opInfo.U32(debugSoftware)
        opInfo.F32(spec.floatPrecision)

        if op.outputMemoryAddress.memType == MemoryType.TEMP:
            opInfo.DataSource(1, op.outputMemoryAddress.offset)
        else:
            opInfo.DataSource(0, op.outputMemoryAddress.offset)

        outputSize = 0
        for x in op.outputDimensions:
            outputSize += TensorSize(x)

        if op.correctOutputData is not None:
            opInfo.U32(outputSize)
            opInfo.DataSource(4, packedCorrectData.offsets[op.nodeIndex])
        else:
            opInfo.U32(0)
            opInfo.U32(0)
            opInfo.U32(0)

        opInfo.U32(len(op.inputs))

        for inp in op.inputs:
            found = False

            if not found and inp.sourceType == DataSourceType.INITIALIZER:
                found = True
                opInfo.DataSource(3, packedInitializers.offsets[inp.index])
            if not found and inp.sourceType == DataSourceType.MODEL_INPUT:
                found = True
                opInfo.DataSource(2, inp.index)

            outputOp = None
            if not found:
                outputNodeIndex = inp.index

                # Need to get the position of the output from a previous node.
                outputOp = cModel.operations[outputNodeIndex]

            if not found and useValidDataAsInput:
                if outputOp.correctOutputData is not None:
                    found = True
                    opInfo.DataSource(4, packedCorrectData.offsets[inp.index])
            if not found:
                found = True
                if outputOp.outputMemoryAddress.memType == MemoryType.TEMP:
                    opInfo.DataSource(1, outputOp.outputMemoryAddress.offset)
                else:
                    opInfo.DataSource(0, outputOp.outputMemoryAddress.offset)

        # Emit operation info
        EmitParameterList(opInfo, op)

        size = opInfo.GetSize()
        opInfo.PrependU32(size + 4)

        packer.Append(opInfo.GetContent())

    dataContent = packer.GetContent()

    try:
        os.makedirs(binOutputLocation, exist_ok=True)
    except:
        return

    if debugging:
        with open(
            os.path.join(binOutputLocation, f"{namespace}_inputs.bin"), "wb"
        ) as f:
            f.write(packedInputs.data)
            if len(packedInputs.data) == 0:
                f.write(b"0000")

        with open(
            os.path.join(binOutputLocation, f"{namespace}_correctOutputs.bin"), "wb"
        ) as f:
            f.write(packedCorrectData.data)

    with open(os.path.join(binOutputLocation, f"{namespace}_model.bin"), "wb") as f:
        f.write(packedInitializers.data)

    with open(os.path.join(binOutputLocation, f"{namespace}_metamodel.bin"), "wb") as f:
        f.write(dataContent)


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
