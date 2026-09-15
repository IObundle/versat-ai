import onnx
from onnx import TensorProto, version_converter
from onnx.helper import (
    make_model,
    make_node,
    make_graph,
    make_tensor_value_info,
    make_opsetid,
)
from onnx import __version__, IR_VERSION
from onnx.defs import onnx_opset_version
from onnx.checker import check_model
from skl2onnx.helpers.onnx_helper import save_onnx_model
from onnx import numpy_helper
from dataclasses import dataclass, fields
from onnxOperators import BroadCastShape, ExtendShape
from pprint import pprint

import sys
import numpy as np
import onnxruntime as ort
import os
import shutil
import hashlib
import random

tests = []
testList = []


@dataclass
class Test:
    tensors: list[any] = None
    outputTensor: any = None
    node: any = None
    randomArrays: list[any] = None
    initializerArrays: list[any] = None


@dataclass
class PaddingType:
    kind: str
    padding: list[int] = None


@dataclass
class ConvArgs:
    shape: list[int]
    features: int
    kernel: list[int]
    strides: list[int]
    dilations: list[int]
    group: int
    bias: bool
    auto_pad: str
    pad: list[int]

    def IsValid(self):
        assert self.auto_pad in ["NOTSET", "SAME_LOWER", "SAME_UPPER", "VALID"]

        assert len(self.shape) == 4

        inputChannels = self.shape[1]

        if self.features % self.group != 0:
            return False
        if inputChannels % self.group != 0:
            return False

        return True

    def Create(self, linear=False):
        global tests
        s = self

        shape = self.shape
        features = self.features
        kernel = self.kernel
        strides = self.strides
        dilations = self.dilations
        group = self.group
        bias = self.bias
        auto_pad = self.auto_pad
        pads = self.pad

        assert self.IsValid()

        testIndex = len(tests)

        inputChannels = shape[1]
        test = Test()

        inputTensor = make_tensor_value_info(
            GetInputTrueName(testIndex, 0), TensorProto.FLOAT, shape
        )

        kernelShape = [features, shape[1] // group, kernel[0], kernel[1]]
        kernelTensor = make_tensor_value_info(
            GetInputTrueName(testIndex, 1), TensorProto.FLOAT, kernelShape
        )

        biasTensor = None
        if bias:
            biasTensor = make_tensor_value_info(
                GetInputTrueName(testIndex, 2), TensorProto.FLOAT, [features]
            )

        # Let onnx infer shape specifics
        outputShape = [None] * len(shape)

        if auto_pad == "NOTSET":
            if pads == None:
                pads = [0, 0, 0, 0]

        if pads:
            assert auto_pad == "NOTSET"

        test.tensors = [inputTensor, kernelTensor]
        if bias:
            test.tensors.append(biasTensor)

        test.outputTensor = make_tensor_value_info(
            GetOutputTrueName(testIndex), TensorProto.FLOAT, outputShape
        )
        inputs = [GetInputTrueName(testIndex, 0), GetInputTrueName(testIndex, 1)]
        if bias:
            inputs.append(GetInputTrueName(testIndex, 2))

        test.node = make_node(
            "Conv",
            inputs,
            [GetOutputTrueName(testIndex)],
            auto_pad=auto_pad,
            group=group,
            dilations=dilations,
            kernel_shape=kernel,
            pads=pads,
            strides=strides,
        )

        randomArray0 = np.random.randn(*shape).astype(np.float32)
        randomArray1 = np.random.randn(*kernelShape).astype(np.float32)

        val = 1.0
        if linear:
            randomArray0 = np.zeros(shape).astype(np.float32)
            for i, x in np.ndenumerate(randomArray0):
                randomArray0[i] = val
                val += 1.0

            randomArray1 = np.zeros(kernelShape).astype(np.float32)
            for i, x in np.ndenumerate(randomArray1):
                randomArray1[i] = val
                val += 1.0

        test.randomArrays = [randomArray0, randomArray1]

        if s.bias:
            randomBias = np.random.randn(s.features).astype(np.float32)

            if linear:
                randomBias = np.zeros([s.features]).astype(np.float32)
                for i, x in np.ndenumerate(randomBias):
                    randomBias[i] = val
                    val += 1.0

            test.randomArrays.append(randomBias)

        tests.append(test)


@dataclass
class PadArgs:
    shape: list[int]
    pads: list[int]

    def Create(self, linear=False):
        global tests
        testIndex = len(tests)

        shape = self.shape
        pads = self.pads

        test = Test()

        # Let onnx infer shape specifics
        outputShape = [None] * len(shape)
        numberInputs = 1

        inputs = [GetInputTrueName(testIndex, x) for x in range(numberInputs)]
        test.tensors = [
            make_tensor_value_info(inputs[0], TensorProto.FLOAT, shape),
        ]

        test.outputTensor = make_tensor_value_info(
            GetOutputTrueName(testIndex), TensorProto.FLOAT, outputShape
        )
        test.node = make_node("Pad", inputs, [GetOutputTrueName(testIndex)], pads=pads)

        # print(test.node,test.tensors,test.outputTensor)

        test.randomArrays = [None, None, None]
        test.randomArrays[0] = np.random.randn(*shape).astype(np.float32)

        tests.append(test)


@dataclass
class BinaryOpArgs:
    op: str
    leftShape: list[int]
    rightShape: list[int]
    forcedOutputShape: list[int]

    def Create(self, linear=False):
        global tests
        testIndex = len(tests)

        test = Test()

        maxDims = max(len(self.leftShape), len(self.rightShape))

        # Let onnx infer shape specifics
        outputShape = [None] * maxDims

        if self.forcedOutputShape:
            outputShape = self.forcedOutputShape

        numberInputs = 2
        shapes = [self.leftShape, self.rightShape]

        inputs = [GetInputTrueName(testIndex, x) for x in range(numberInputs)]
        test.tensors = [
            make_tensor_value_info(x, TensorProto.FLOAT, shapes[i])
            for i, x in enumerate(inputs)
        ]

        test.outputTensor = make_tensor_value_info(
            GetOutputTrueName(testIndex), TensorProto.FLOAT, outputShape
        )
        test.node = make_node(
            self.op,
            inputs,
            [GetOutputTrueName(testIndex)],
        )

        test.randomArrays = [np.random.randn(*x).astype(np.float32) for x in shapes]

        tests.append(test)


@dataclass
class UnaryOpArgs:
    op: str
    shape: list[int]

    def Create(self, linear=False):
        global tests
        testIndex = len(tests)

        maxDims = len(self.shape)

        # Let onnx infer shape specifics
        outputShape = [None] * maxDims

        test = Test()

        numberInputs = 1
        shapes = [self.shape]

        inputs = [GetInputTrueName(testIndex, x) for x in range(numberInputs)]
        test.tensors = [
            make_tensor_value_info(x, TensorProto.FLOAT, shapes[i])
            for i, x in enumerate(inputs)
        ]

        test.outputTensor = make_tensor_value_info(
            GetOutputTrueName(testIndex), TensorProto.FLOAT, outputShape
        )
        test.node = make_node(
            self.op,
            inputs,
            [GetOutputTrueName(testIndex)],
        )

        test.randomArrays = [np.random.randn(*x).astype(np.float32) for x in shapes]

        tests.append(test)


@dataclass
class MaxPoolArgs:
    shape: list[int]
    kernel: list[int]
    strides: list[int]
    auto_pad: str = "NOTSET"
    pads: list[int] = None

    def Create(self, linear=False):
        global tests
        testIndex = len(tests)

        shape = self.shape
        auto_pad = self.auto_pad
        pads = self.pads

        test = Test()

        tensor = make_tensor_value_info(
            GetInputTrueName(testIndex, 0), TensorProto.FLOAT, shape
        )

        # Let onnx infer shape specifics
        outputShape = [None] * len(shape)

        if auto_pad == "NOTSET":
            if pads == None:
                pads = [0, 0, 0, 0]

        if pads:
            assert auto_pad == "NOTSET"

        test.tensors = [tensor]
        test.outputTensor = make_tensor_value_info(
            GetOutputTrueName(testIndex), TensorProto.FLOAT, outputShape
        )
        test.node = make_node(
            "MaxPool",
            [GetInputTrueName(testIndex, 0)],
            [GetOutputTrueName(testIndex)],
            kernel_shape=self.kernel,
            strides=self.strides,
            auto_pad=auto_pad,
            pads=self.pads,
        )

        randomArray = np.random.randn(*shape).astype(np.float32)
        test.randomArrays = [randomArray]

        tests.append(test)


@dataclass
class AveragePoolArgs:
    shape: list[int]
    kernel: list[int]
    strides: list[int]
    auto_pad: str = "NOTSET"
    pads: list[int] = None

    def Create(self, linear=False):
        global tests
        testIndex = len(tests)

        shape = self.shape
        kernel = self.kernel
        strides = self.strides
        auto_pad = self.auto_pad
        pads = self.pads

        test = Test()

        tensor = make_tensor_value_info(
            GetInputTrueName(testIndex, 0), TensorProto.FLOAT, shape
        )

        # Let onnx infer shape specifics
        outputShape = [None] * len(shape)

        if auto_pad == "NOTSET":
            if pads == None:
                pads = [0, 0, 0, 0]

        if pads:
            assert auto_pad == "NOTSET"

        test.tensors = [tensor]
        test.outputTensor = make_tensor_value_info(
            GetOutputTrueName(testIndex), TensorProto.FLOAT, outputShape
        )
        test.node = make_node(
            "AveragePool",
            [GetInputTrueName(testIndex, 0)],
            [GetOutputTrueName(testIndex)],
            kernel_shape=kernel,
            strides=strides,
            auto_pad=auto_pad,
            pads=pads,
        )

        randomArray = np.random.randn(*shape).astype(np.float32)
        test.randomArrays = [randomArray]

        tests.append(test)


@dataclass
class ReshapeArgs:
    shapeIn: list[int]
    shapeOut: list[int]

    def Create(self, linear=False):
        global tests
        testIndex = len(tests)

        shapeIn = self.shapeIn
        shapeOut = self.shapeOut

        test = Test()

        val = np.array(shapeOut, dtype=np.int64)
        A = numpy_helper.from_array(val, name=GetInitializerTrueName(testIndex))

        tensor = make_tensor_value_info(
            GetInputTrueName(testIndex, 0), TensorProto.FLOAT, shapeIn
        )

        test.tensors = [tensor]
        test.outputTensor = make_tensor_value_info(
            GetOutputTrueName(testIndex), TensorProto.FLOAT, shapeOut
        )
        test.node = make_node(
            "Reshape",
            [GetInputTrueName(testIndex, 0), GetInitializerTrueName(testIndex)],
            [GetOutputTrueName(testIndex)],
        )

        randomArray = np.random.randn(*shapeIn).astype(np.float32)
        test.randomArrays = [randomArray]
        test.initializerArrays = [A]

        tests.append(test)


@dataclass
class TransposeArgs:
    shapeIn: list[int]
    permutations: list[int]

    def Create(self, linear=False):
        global tests
        testIndex = len(tests)

        shapeIn = self.shapeIn
        shapeOut = [0] * len(self.shapeIn)

        for i, perm in enumerate(self.permutations):
            shapeOut[i] = shapeIn[perm]

        test = Test()

        tensor = make_tensor_value_info(
            GetInputTrueName(testIndex, 0), TensorProto.FLOAT, shapeIn
        )

        test.tensors = [tensor]
        test.outputTensor = make_tensor_value_info(
            GetOutputTrueName(testIndex), TensorProto.FLOAT, shapeOut
        )
        test.node = make_node(
            "Transpose",
            [GetInputTrueName(testIndex, 0)],
            [GetOutputTrueName(testIndex)],
            perm=self.permutations,
        )

        randomArray = np.random.randn(*shapeIn).astype(np.float32)
        test.randomArrays = [randomArray]

        tests.append(test)


@dataclass
class SoftmaxArgs:
    shape: list[int]
    axis: int

    def Create(self, linear=False):
        global tests
        testIndex = len(tests)

        shape = self.shape
        axis = self.axis

        test = Test()

        tensor = make_tensor_value_info(
            GetInputTrueName(testIndex, 0), TensorProto.FLOAT, shape
        )
        test.tensors = [tensor]

        shapeOut = [None] * len(shape)
        test.outputTensor = make_tensor_value_info(
            GetOutputTrueName(testIndex), TensorProto.FLOAT, shapeOut
        )
        test.node = make_node(
            "Softmax",
            [GetInputTrueName(testIndex, 0)],
            [GetOutputTrueName(testIndex)],
            axis=axis,
        )

        randomArray = np.random.randn(*shape).astype(np.float32)
        test.randomArrays = [randomArray]

        tests.append(test)


@dataclass(frozen=True)
class BatchNormalizationArgs:
    shape: list[int]
    epsilon: float
    momentum: float

    def Create(self, linear=False):
        global tests
        testIndex = len(tests)

        maxDims = len(self.shape)

        # Let onnx infer shape specifics
        outputShape = [None] * maxDims

        C = 1
        if len(self.shape) > 1:
            C = self.shape[1]

        test = Test()

        numberInputs = 5
        shapes = [self.shape, [C], [C], [C], [C]]

        inputs = [GetInputTrueName(testIndex, x) for x in range(numberInputs)]
        test.tensors = [
            make_tensor_value_info(x, TensorProto.FLOAT, shapes[i])
            for i, x in enumerate(inputs)
        ]

        test.outputTensor = make_tensor_value_info(
            GetOutputTrueName(testIndex), TensorProto.FLOAT, outputShape
        )
        test.node = make_node(
            "BatchNormalization",
            inputs,
            [GetOutputTrueName(testIndex)],
            epsilon=self.epsilon,
            momentum=self.momentum,
        )

        test.randomArrays = [np.random.randn(*x).astype(np.float32) for x in shapes]

        tests.append(test)


def GetInputTrueName(testIndex, inputIndex):
    VARS = "XYZABC"
    assert inputIndex < len(VARS)

    return f"{VARS[inputIndex]}{testIndex}"


def GetOutputTrueName(testIndex):
    return f"OUT{testIndex}"


def GetInitializerTrueName(testIndex):
    return f"A{testIndex}"


def CreateBinaryOpTest(op, leftShape, rightShape, forcedOutputShape=None):
    global testList
    testList.append(BinaryOpArgs(op, leftShape, rightShape, forcedOutputShape))


def CreatePad(shape, pads):
    global testList
    testList.append(PadArgs(shape, pads))


def CreateUnaryOpTest(op, shape):
    global testList
    testList.append(UnaryOpArgs(op, shape))


def CreateConvolution(
    shape,
    features,
    kernel,
    strides,
    dilations,
    group=1,
    bias: bool = False,
    auto_pad="NOTSET",
    pads=None,
):
    global testList
    conv = ConvArgs(
        shape, features, kernel, strides, dilations, group, bias, auto_pad, pads
    )

    if conv.IsValid():
        testList.append(conv)


def CreateMaxPool(shape, kernel, strides, auto_pad="NOTSET", pads=None):
    global testList
    testList.append(MaxPoolArgs(shape, kernel, strides, auto_pad, pads))


def CreateAveragePool(shape, kernel, strides, auto_pad="NOTSET", pads=None):
    global testList
    testList.append(AveragePoolArgs(shape, kernel, strides, auto_pad, pads))


def CreateReshape(shapeIn, shapeOut):
    global testList
    testList.append(ReshapeArgs(shapeIn, shapeOut))


def CreateTranspose(shapeIn, shapeOut):
    global testList
    testList.append(TransposeArgs(shapeIn, shapeOut))


def CreateSoftmax(shape, axis=-1):
    global testList
    testList.append(SoftmaxArgs(shape, axis))


def CreateBatchNormalization(shape, epsilon=None, momentum=None):
    global testList
    testList.append(BatchNormalizationArgs(shape, epsilon, momentum))


def CreateBinaryOpDynamicTest(leftShape, rightShape, actualLeft, actualRight):
    global tests

    maxDims = max(len(leftShape), len(rightShape))

    # Let onnx infer shape specifics
    outputShape = [None] * maxDims

    testIndex = len(tests)

    test = Test()

    leftTensor = make_tensor_value_info(
        GetInputTrueName(testIndex, 0), TensorProto.FLOAT, leftShape
    )
    rightTensor = make_tensor_value_info(
        GetInputTrueName(testIndex, 1), TensorProto.FLOAT, rightShape
    )

    test.tensors = [leftTensor, rightTensor]
    test.outputTensor = make_tensor_value_info(
        GetOutputTrueName(testIndex), TensorProto.FLOAT, outputShape
    )
    test.node = make_node(
        "Add",
        [GetInputTrueName(testIndex, 0), GetInputTrueName(testIndex, 1)],
        [GetOutputTrueName(testIndex)],
    )

    leftRandomArray = np.random.randn(*actualLeft).astype(np.float32)
    rightRandomArray = np.random.randn(*actualRight).astype(np.float32)
    test.randomArrays = [leftRandomArray, rightRandomArray]

    tests.append(test)


@dataclass(frozen=True)
class LRNArgs:
    shape: list[int]
    size: int
    alpha: float
    beta: float
    bias: float

    def Create(self, linear=False):
        global tests
        testIndex = len(tests)

        maxDims = len(self.shape)

        # Let onnx infer shape specifics
        outputShape = [None] * maxDims

        test = Test()

        numberInputs = 1
        shapes = [self.shape]

        inputs = [GetInputTrueName(testIndex, x) for x in range(numberInputs)]
        test.tensors = [
            make_tensor_value_info(x, TensorProto.FLOAT, shapes[i])
            for i, x in enumerate(inputs)
        ]

        test.outputTensor = make_tensor_value_info(
            GetOutputTrueName(testIndex), TensorProto.FLOAT, outputShape
        )
        test.node = make_node(
            "LRN",
            inputs,
            [GetOutputTrueName(testIndex)],
            alpha=self.alpha,
            beta=self.beta,
            bias=self.bias,
            size=self.size,
        )

        test.randomArrays = [np.random.randn(*x).astype(np.float32) for x in shapes]

        tests.append(test)


def CreateLRN(shape, size, alpha, beta, bias):
    global testList
    testList.append(LRNArgs(shape, size, alpha, beta, bias))


@dataclass(frozen=True)
class DropoutArgs:
    shape: list[int]
    ratio: float

    def Create(self, linear=False):
        global tests
        testIndex = len(tests)

        maxDims = len(self.shape)

        # Let onnx infer shape specifics
        outputShape = [None] * maxDims

        test = Test()

        numberInputs = 1
        shapes = [self.shape]

        inputs = [GetInputTrueName(testIndex, x) for x in range(numberInputs)]
        test.tensors = [
            make_tensor_value_info(x, TensorProto.FLOAT, shapes[i])
            for i, x in enumerate(inputs)
        ]

        test.outputTensor = make_tensor_value_info(
            GetOutputTrueName(testIndex), TensorProto.FLOAT, outputShape
        )
        test.node = make_node(
            "Dropout",
            inputs,
            [GetOutputTrueName(testIndex)],
            ratio=self.ratio,
        )

        test.randomArrays = [np.random.randn(*x).astype(np.float32) for x in shapes]

        tests.append(test)


def CreateLRN(shape, size, alpha, beta, bias):
    global testList
    testList.append(LRNArgs(shape, size, alpha, beta, bias))


def CreateDropout(shape, ratio):
    global testList
    testList.append(DropoutArgs(shape, ratio))


@dataclass
class GemmArgs:
    aShape: list[int]
    bShape: list[int]
    cShape: list[int]
    alpha: float
    beta: float
    transA: int
    transB: int

    def IsValid(self):
        aShape = self.aShape
        if self.transA:
            aShape = [aShape[1], aShape[0]]
        bShape = self.bShape
        if self.transB:
            bShape = [bShape[1], bShape[0]]
        cShape = self.cShape
        if not self.cShape:
            cShape = [1, 1]
        if len(cShape) == 1:
            cShape = [1, cShape[0]]

        outShape = [aShape[0], bShape[1]]

        # print("A",aShape,"B",bShape,"C",cShape,"O",outShape)

        if aShape[1] != bShape[0]:
            return False
        if cShape[0] != 1 and cShape[0] != outShape[0]:
            return False
        if cShape[1] != 1 and cShape[1] != outShape[1]:
            return False

        return True

    def Create(self, linear=False):
        global tests
        testIndex = len(tests)

        assert self.IsValid()

        test = Test()

        maxDims = max(len(self.aShape), len(self.bShape))

        # Let onnx infer shape specifics
        outputShape = [None] * maxDims

        cShape = self.cShape
        if not self.cShape:
            cShape = [1, 1]

        numberInputs = 3
        shapes = [self.aShape, self.bShape, cShape]

        inputs = [GetInputTrueName(testIndex, x) for x in range(numberInputs)]
        test.tensors = [
            make_tensor_value_info(x, TensorProto.FLOAT, shapes[i])
            for i, x in enumerate(inputs)
        ]

        test.outputTensor = make_tensor_value_info(
            GetOutputTrueName(testIndex), TensorProto.FLOAT, outputShape
        )
        test.node = make_node(
            "Gemm",
            inputs,
            [GetOutputTrueName(testIndex)],
            alpha=self.alpha,
            beta=self.beta,
            transA=self.transA,
            transB=self.transB,
        )

        test.randomArrays = [np.random.randn(*x).astype(np.float32) for x in shapes]

        if not self.cShape:
            test.randomArrays[2] = np.zeros(cShape).astype(np.float32)

        tests.append(test)


def CreateGemm(aShape, bShape, cShape=None, alpha=1.0, beta=1.0, transA=0, transB=0):
    global testList
    testList.append(GemmArgs(aShape, bShape, cShape, alpha, beta, transA, transB))


@dataclass
class GenerateTestConfig:
    testAdd: int = 0
    testRelu: int = 0
    testReshape: int = 0
    testTranspose: int = 0
    testMaxPool: int = 0
    testAveragePool: int = 0
    testMatMul: int = 0
    testDropout: int = 0
    testGemm: int = 0
    testConv: int = 0
    testBatchNormalization: int = 0
    testSoftmax: int = 0
    testLRN: int = 0
    testPad: int = 0
    generateOneOfEach: int = 0
    generativeTests: int = 0
    testBig: int = 0


def GenerateSimpleTest(config):
    testComplexity = 0

    # MARK4
    # Small test

    if config.generateOneOfEach:
        CreateSoftmax([1], 0)
        CreateReshape([4, 2], [8])
        CreateMaxPool([1, 1, 4, 4], [2, 2], [2, 2], "NOTSET", [0, 0, 0, 0])
        CreateUnaryOpTest("Relu", [4])
        CreateLRN([1, 3, 2, 2], int(3), 0.5, 0.35, 0.5)
        CreateBatchNormalization([1, 1, 1, 1])
        CreateBinaryOpTest("Add", [3, 2], [3, 2])
        CreateTranspose([2, 2], [0, 1])
        CreateBinaryOpTest("MatMul", [2, 1, 3], [3, 4])
        CreateAveragePool([1, 1, 4, 4], [2, 2], [2, 2], "NOTSET", [0, 0, 0, 0])
        CreateGemm([2, 2], [2, 2])
        CreateConvolution([1, 2, 2, 2], 2, [2, 2], [2, 2], [1, 1], 1)

    # MARK1
    testAdd = config.testAdd
    testRelu = config.testRelu
    testReshape = config.testReshape
    testTranspose = config.testTranspose
    testMaxPool = config.testMaxPool
    testAveragePool = config.testAveragePool
    testMatMul = config.testMatMul
    testDropout = config.testDropout
    testGemm = config.testGemm
    testConv = config.testConv
    testBatchNormalization = config.testBatchNormalization
    testSoftmax = config.testSoftmax
    testLRN = config.testLRN
    generativeTests = config.generativeTests
    testBig = config.testBig

    if testGemm:
        CreateGemm([1, 2], [2, 3], [1, 1], 2.0, 2.0)
        CreateGemm([1, 4], [4, 1], [1, 1], 2.0, 2.0)
        CreateGemm([4, 1], [1, 4], [1, 1], 2.0, 2.0)
        CreateGemm([4, 1], [1, 4], [4, 1], 2.0, 2.0)
        CreateGemm([4, 1], [1, 4], [1, 4], 2.0, 2.0)
        CreateGemm([4, 1], [1, 4], [4, 4], 2.0, 2.0)
        CreateGemm([4, 1], [1, 4], [1, 4], 2.0, 2.0, 1, 0)

        if generativeTests:
            aShapes = [[4, 1], [4, 2], [4, 4], [2, 4], [1, 4]]
            bShapes = [[1, 4], [2, 4], [4, 4], [4, 2], [4, 1]]
            cShapes = [None, [1, 1], [2, 1], [1, 2], [4, 1], [1, 4]]
            alphas = [1.0, 2.0]
            betas = [1.0, 2.0]
            transA = [0, 1]
            transB = [0, 1]

            for a in aShapes:
                for b in bShapes:
                    for c in cShapes:
                        for alpha in alphas:
                            for beta in betas:
                                for tA in transA:
                                    for tB in transB:
                                        CreateGemm(a, b, c, alpha, beta, tA, tB)

    if testLRN:
        CreateLRN([1, 3, 2, 2], int(3), 0.5, 0.35, 0.5)
        CreateLRN([1, 4, 4, 4], int(3), 0.0001, 0.75, 1.0)
        CreateLRN([1, 11, 6, 6], int(5), 0.0001, 0.75, 1.0)
        CreateLRN([1, 11, 8, 8], int(5), 0.0001, 0.75, 1.0)
        CreateLRN([1, 11, 10, 10], int(5), 0.0001, 0.75, 1.0)
        CreateLRN([1, 6, 3, 3], int(5), 0.0001, 0.75, 1.0)
        CreateLRN([1, 6, 5, 5], int(5), 0.0001, 0.75, 1.0)
        CreateLRN([1, 7, 1, 1], int(3), 0.0001, 0.65, 1.5)
        CreateLRN([1, 7, 3, 3], int(3), 0.0001, 0.65, 1.5)
        CreateLRN([1, 7, 5, 5], int(3), 0.0001, 0.65, 1.5)
        CreateLRN([1, 11, 1, 1], int(5), 0.0002, 0.85, 2.0)
        CreateLRN([1, 11, 3, 3], int(5), 0.0002, 0.85, 2.0)
        CreateLRN([1, 11, 5, 5], int(5), 0.0002, 0.85, 2.0)

    if testDropout:
        # No point in complex tests, dropout in inference is just a copy from input to output.
        CreateDropout([1, 1, 1, 1], 0.5)
        CreateDropout([1, 1, 2, 2], 0.5)
        CreateDropout([1, 2, 2, 2], 0.5)
        CreateDropout([4, 4, 4, 4], 1.0)

    if testBatchNormalization:
        for t in [2, 10]:
            CreateBatchNormalization([1, 1, 1, 1])
            CreateBatchNormalization([1, 1, 1, t])
            CreateBatchNormalization([1, 1, t, 1])
            CreateBatchNormalization([1, t, 1, 1])
            CreateBatchNormalization([t, 1, 1, 1])
            CreateBatchNormalization([1, 1, t, t])
            CreateBatchNormalization([1, t, 1, t])
            CreateBatchNormalization([t, 1, 1, t])
            CreateBatchNormalization([1, t, t, 1])
            CreateBatchNormalization([2, 1, t, 1])
            CreateBatchNormalization([t, t, 1, 1])
            CreateBatchNormalization([t, t, 1, 1])
            CreateBatchNormalization([1, t, t, t])
            CreateBatchNormalization([t, 1, t, t])
            CreateBatchNormalization([t, t, 1, t])
            CreateBatchNormalization([t, t, t, 1])
            CreateBatchNormalization([t, t, t, t])

        # Big examples to trigger memory exhaustion problems.
        CreateBatchNormalization([2, 2, 100, 100])

    if testSoftmax:
        # Softmax axis come in pairs.
        # If the dim is N, then the pairs are X and X - N.
        # For dim=2, pairs are 0,-2 and 1,-1
        # For dim=3, pairs are 0,-3 , 1,-2 and 2,-1
        # Softmax sums everything to the "right" of (and including) the axis used.
        # For the 2D example, 0 is everything
        # While 1 is everything to the right of the y dim (which means that we iterate the y dim).

        # For the 3D example, 0 is everything
        #                     1 is everything right of Z (iterate Z).
        #                     2 is everything right of Y (iterate Z and Y).

        w = 5
        z = 4
        y = 3
        x = 2

        if testBig:
            CreateSoftmax([256, 256], 0)

        CreateSoftmax([1], 0)
        CreateSoftmax([2], 0)
        CreateSoftmax([10], 0)

        CreateSoftmax([y, x], -2)  # A
        CreateSoftmax([y, x], -1)  # B
        CreateSoftmax([y, x], 0)  # A
        CreateSoftmax([y, x], 1)  # B

        CreateSoftmax([z, y, x], -3)  # A
        CreateSoftmax([z, y, x], -2)  # B
        CreateSoftmax([z, y, x], -1)  # C
        CreateSoftmax([z, y, x], 0)  # A
        CreateSoftmax([z, y, x], 1)  # B
        CreateSoftmax([z, y, x], 2)  # C

        CreateSoftmax([w, z, y, x], -4)  # A
        CreateSoftmax([w, z, y, x], -3)  # B
        CreateSoftmax([w, z, y, x], -2)  # C
        CreateSoftmax([w, z, y, x], -1)  # D
        CreateSoftmax([w, z, y, x], 0)  # A
        CreateSoftmax([w, z, y, x], 1)  # B
        CreateSoftmax([w, z, y, x], 2)  # C
        CreateSoftmax([w, z, y, x], 3)  # D

    if testAdd:
        CreateBinaryOpTest("Add", [1], [1])
        CreateBinaryOpTest("Add", [2], [2])
        CreateBinaryOpTest("Add", [3, 2], [3, 2])
        CreateBinaryOpTest("Add", [4, 5], [2, 3, 4, 5])

        # Simplest tests, no broadcast or abusing dimensions
        CreateBinaryOpTest("Add", [1], [1])
        CreateBinaryOpTest("Add", [4], [4])
        CreateBinaryOpTest("Add", [2, 4], [2, 4])
        CreateBinaryOpTest("Add", [2, 4, 6], [2, 4, 6])
        CreateBinaryOpTest("Add", [2, 4, 6, 8], [2, 4, 6, 8])

        # Broadcasting
        CreateBinaryOpTest("Add", [2, 3, 4, 5], [1])
        CreateBinaryOpTest("Add", [2, 3, 4, 5], [5])
        CreateBinaryOpTest("Add", [4, 5], [2, 3, 4, 5])
        CreateBinaryOpTest("Add", [1, 4, 5], [2, 3, 1, 1])
        CreateBinaryOpTest("Add", [3, 4, 5], [2, 1, 1, 1])

        if testBig:
            CreateBinaryOpTest("Add", [10240], [10240])
            CreateBinaryOpTest("Add", [10240], [1])

    if testRelu:
        CreateUnaryOpTest("Relu", [1])
        CreateUnaryOpTest("Relu", [4])
        CreateUnaryOpTest("Relu", [2, 4])
        CreateUnaryOpTest("Relu", [2, 4, 6])
        CreateUnaryOpTest("Relu", [2, 4, 6, 8])

        if testBig:
            CreateUnaryOpTest("Relu", [4096])
            CreateUnaryOpTest("Relu", [1024, 1024])

    if testReshape:
        CreateReshape([4, 2], [8])
        CreateReshape([4, 2], [2, 4])
        CreateReshape([1, 8], [8])
        CreateReshape([2, 3, 4], [24])
        CreateReshape([24], [2, 3, 4])
        CreateReshape([24], [4, 3, 2])

    if testTranspose:
        CreateTranspose([2, 2], [0, 1])
        CreateTranspose([2, 2], [1, 0])
        CreateTranspose([2, 3], [0, 1])
        CreateTranspose([2, 3], [1, 0])
        CreateTranspose([2, 3, 4], [0, 1, 2])
        CreateTranspose([2, 3, 4], [0, 2, 1])
        CreateTranspose([2, 3, 4], [1, 0, 2])
        CreateTranspose([2, 3, 4], [2, 0, 1])
        CreateTranspose([2, 3, 4], [1, 2, 0])
        CreateTranspose([2, 3, 4], [2, 1, 0])

    if testMatMul:
        # Matrices of sizes different than 2 are supported by ONNX by broadcasting the inner 2 dimensions
        # TODO: While we are looking at graph optimizations do not want to deal with non 2 dims examples.
        if False:
            CreateBinaryOpTest("MatMul", [2, 1, 3], [3, 4])
            CreateBinaryOpTest("MatMul", [2, 1, 1, 3], [3, 4])
            CreateBinaryOpTest("MatMul", [2, 2, 1, 3], [3, 4])
            CreateBinaryOpTest("MatMul", [2, 1, 1, 1, 3], [3, 4])
            CreateBinaryOpTest("MatMul", [2, 2, 1, 1, 3], [3, 4])
            CreateBinaryOpTest("MatMul", [2, 2, 2, 1, 3], [3, 4])
            CreateBinaryOpTest("MatMul", [1, 1], [1], [1])
            CreateBinaryOpTest("MatMul", [1], [1, 1], [1])
            CreateBinaryOpTest("MatMul", [1, 2, 3], [3, 4])
            CreateBinaryOpTest("MatMul", [1, 1, 3], [3, 4])
            CreateBinaryOpTest("MatMul", [1, 1, 1, 1, 1], [1, 1])
            CreateBinaryOpTest("MatMul", [1, 1, 1, 2, 1], [1, 1])
            CreateBinaryOpTest("MatMul", [1, 1, 2, 1, 1], [1, 1])
            CreateBinaryOpTest("MatMul", [1, 2, 1, 1, 1], [1, 1])
            CreateBinaryOpTest("MatMul", [2, 1, 1, 1, 1], [1, 1])
            CreateBinaryOpTest("MatMul", [1, 1, 1, 1, 3], [3, 4])
            CreateBinaryOpTest("MatMul", [1, 1, 1, 2, 3], [3, 4])
            CreateBinaryOpTest("MatMul", [1, 1, 2, 1, 3], [3, 4])
            CreateBinaryOpTest("MatMul", [1, 2, 1, 1, 3], [3, 4])
            CreateBinaryOpTest("MatMul", [2, 1, 1, 1, 3], [3, 4])
            CreateBinaryOpTest("MatMul", [1, 1], [1, 1, 1, 1, 1])
            CreateBinaryOpTest("MatMul", [1, 2], [1, 1, 1, 2, 1])
            CreateBinaryOpTest("MatMul", [4, 2], [1, 1, 1, 2, 1])

        # The more common matrices operations are just
        CreateBinaryOpTest("MatMul", [1, 1], [1, 1])
        CreateBinaryOpTest("MatMul", [1, 2], [2, 1])
        CreateBinaryOpTest("MatMul", [2, 1], [1, 2])
        CreateBinaryOpTest("MatMul", [2, 2], [2, 2])
        CreateBinaryOpTest("MatMul", [2, 3], [3, 2])
        CreateBinaryOpTest("MatMul", [3, 2], [2, 3])
        CreateBinaryOpTest("MatMul", [2, 4], [4, 8])
        CreateBinaryOpTest("MatMul", [8, 4], [4, 2])
        CreateBinaryOpTest("MatMul", [10, 11], [11, 20])
        CreateBinaryOpTest("MatMul", [20, 30], [30, 40])
        CreateBinaryOpTest("MatMul", [40, 30], [30, 20])
        CreateBinaryOpTest("MatMul", [50, 50], [50, 50])

        if testBig:
            CreateBinaryOpTest("MatMul", [100, 200], [200, 300])

    # No padding                                           T  L  B  R
    # CreateMaxPool([1, 1, 4, 3], [2, 2], [2, 2], "NOTSET", [0, 1, 0, 0])
    if testMaxPool:
        # All padding posibilities, mostly to test the window generation
        # Padding                                              T  L  B  R
        CreateMaxPool([1, 1, 4, 4], [2, 2], [2, 2], "NOTSET", [0, 0, 0, 0])
        CreateMaxPool([1, 1, 3, 4], [2, 2], [2, 2], "NOTSET", [1, 0, 0, 0])
        CreateMaxPool([1, 1, 4, 3], [2, 2], [2, 2], "NOTSET", [0, 1, 0, 0])
        CreateMaxPool([1, 1, 3, 4], [2, 2], [2, 2], "NOTSET", [0, 0, 1, 0])
        CreateMaxPool([1, 1, 4, 3], [2, 2], [2, 2], "NOTSET", [0, 0, 0, 1])
        CreateMaxPool([1, 1, 3, 3], [2, 2], [2, 2], "NOTSET", [1, 1, 0, 0])
        CreateMaxPool([1, 1, 2, 4], [2, 2], [2, 2], "NOTSET", [1, 0, 1, 0])
        CreateMaxPool([1, 1, 3, 3], [2, 2], [2, 2], "NOTSET", [1, 0, 0, 1])
        CreateMaxPool([1, 1, 3, 3], [2, 2], [2, 2], "NOTSET", [0, 1, 1, 0])
        CreateMaxPool([1, 1, 4, 2], [2, 2], [2, 2], "NOTSET", [0, 1, 0, 1])
        CreateMaxPool([1, 1, 3, 3], [2, 2], [2, 2], "NOTSET", [0, 0, 1, 1])
        CreateMaxPool([1, 1, 2, 3], [2, 2], [2, 2], "NOTSET", [1, 1, 1, 0])
        CreateMaxPool([1, 1, 3, 2], [2, 2], [2, 2], "NOTSET", [1, 1, 0, 1])
        CreateMaxPool([1, 1, 2, 3], [2, 2], [2, 2], "NOTSET", [1, 0, 1, 1])
        CreateMaxPool([1, 1, 3, 2], [2, 2], [2, 2], "NOTSET", [0, 1, 1, 1])
        CreateMaxPool([1, 1, 2, 2], [2, 2], [2, 2], "NOTSET", [1, 1, 1, 1])
        CreateMaxPool([1, 1, 1, 1], [3, 3], [3, 3], "NOTSET", [1, 1, 1, 1])
        CreateMaxPool([1, 1, 10, 10], [2, 2], [2, 2], "NOTSET", [1, 1, 1, 1])

        # Test different kernels, strides, no padding
        CreateMaxPool([1, 3, 8, 8], [2, 2], [2, 2])
        CreateMaxPool([1, 3, 9, 9], [3, 3], [3, 3])
        CreateMaxPool([1, 3, 9, 8], [3, 2], [3, 2])
        CreateMaxPool([1, 3, 8, 9], [2, 3], [2, 3])

        # Different auto pad, minimal size
        CreateMaxPool([1, 3, 1, 1], [2, 2], [2, 2], "SAME_UPPER")
        CreateMaxPool([1, 3, 3, 3], [2, 2], [2, 2], "SAME_UPPER")
        CreateMaxPool([1, 3, 5, 5], [2, 2], [2, 2], "SAME_UPPER")

        CreateMaxPool([1, 3, 1, 1], [2, 2], [2, 2], "SAME_LOWER")
        CreateMaxPool([1, 3, 3, 3], [2, 2], [2, 2], "SAME_LOWER")
        CreateMaxPool([1, 3, 5, 5], [2, 2], [2, 2], "SAME_LOWER")

        # Different auto pad, larger size
        CreateMaxPool([1, 3, 8, 8], [3, 2], [2, 3], "SAME_UPPER")
        CreateMaxPool([1, 3, 8, 8], [2, 3], [3, 2], "SAME_UPPER")
        CreateMaxPool([1, 3, 8, 8], [3, 3], [2, 2], "SAME_UPPER")
        CreateMaxPool([1, 3, 8, 8], [2, 2], [3, 3], "SAME_UPPER")
        CreateMaxPool([1, 3, 8, 8], [3, 2], [2, 3], "SAME_LOWER")
        CreateMaxPool([1, 3, 8, 8], [2, 3], [3, 2], "SAME_LOWER")
        CreateMaxPool([1, 3, 8, 8], [3, 3], [2, 2], "SAME_LOWER")
        CreateMaxPool([1, 3, 8, 8], [2, 2], [3, 3], "SAME_LOWER")
        CreateMaxPool([1, 3, 8, 8], [3, 2], [2, 3], "VALID")
        CreateMaxPool([1, 3, 8, 8], [2, 3], [3, 2], "VALID")
        CreateMaxPool([1, 3, 8, 8], [3, 3], [2, 2], "VALID")
        CreateMaxPool([1, 3, 8, 8], [2, 2], [3, 3], "VALID")

        # Larger example and larger kernel
        CreateMaxPool([1, 3, 5, 5], [20, 20], [20, 20], "SAME_UPPER")
        CreateMaxPool([1, 3, 5, 5], [30, 20], [20, 30], "SAME_UPPER")
        CreateMaxPool([1, 3, 5, 5], [20, 30], [30, 20], "SAME_UPPER")
        CreateMaxPool([1, 3, 5, 5], [30, 30], [20, 20], "SAME_UPPER")
        CreateMaxPool([1, 3, 5, 5], [20, 20], [30, 30], "SAME_UPPER")

        CreateMaxPool([1, 3, 5, 5], [20, 20], [20, 20], "SAME_LOWER")
        CreateMaxPool([1, 3, 5, 5], [30, 20], [20, 30], "SAME_LOWER")
        CreateMaxPool([1, 3, 5, 5], [20, 30], [30, 20], "SAME_LOWER")
        CreateMaxPool([1, 3, 5, 5], [30, 30], [20, 20], "SAME_LOWER")
        CreateMaxPool([1, 3, 5, 5], [20, 20], [30, 30], "SAME_LOWER")

        # Common example
        CreateMaxPool([1, 3, 32, 32], [2, 2], [2, 2], "VALID")

        # 4 D - Not supported by runtime so cannot generate test

    if testAveragePool:
        # All padding posibilities, mostly to test the window generation
        CreateAveragePool([1, 1, 2, 2], [2, 2], [2, 2], "NOTSET", [0, 0, 0, 0])

        # No padding                                               T  L  B  R
        CreateAveragePool([1, 1, 4, 4], [2, 2], [2, 2], "NOTSET", [0, 0, 0, 0])
        CreateAveragePool([1, 1, 3, 4], [2, 2], [2, 2], "NOTSET", [1, 0, 0, 0])
        CreateAveragePool([1, 1, 4, 3], [2, 2], [2, 2], "NOTSET", [0, 1, 0, 0])
        CreateAveragePool([1, 1, 3, 4], [2, 2], [2, 2], "NOTSET", [0, 0, 1, 0])
        CreateAveragePool([1, 1, 4, 3], [2, 2], [2, 2], "NOTSET", [0, 0, 0, 1])
        CreateAveragePool([1, 1, 3, 3], [2, 2], [2, 2], "NOTSET", [1, 1, 0, 0])
        CreateAveragePool([1, 1, 2, 4], [2, 2], [2, 2], "NOTSET", [1, 0, 1, 0])
        CreateAveragePool([1, 1, 3, 3], [2, 2], [2, 2], "NOTSET", [1, 0, 0, 1])
        CreateAveragePool([1, 1, 3, 3], [2, 2], [2, 2], "NOTSET", [0, 1, 1, 0])
        CreateAveragePool([1, 1, 4, 2], [2, 2], [2, 2], "NOTSET", [0, 1, 0, 1])
        CreateAveragePool([1, 1, 3, 3], [2, 2], [2, 2], "NOTSET", [0, 0, 1, 1])
        CreateAveragePool([1, 1, 2, 3], [2, 2], [2, 2], "NOTSET", [1, 1, 1, 0])
        CreateAveragePool([1, 1, 3, 2], [2, 2], [2, 2], "NOTSET", [1, 1, 0, 1])
        CreateAveragePool([1, 1, 2, 3], [2, 2], [2, 2], "NOTSET", [1, 0, 1, 1])
        CreateAveragePool([1, 1, 3, 2], [2, 2], [2, 2], "NOTSET", [0, 1, 1, 1])
        CreateAveragePool([1, 1, 2, 2], [2, 2], [2, 2], "NOTSET", [1, 1, 1, 1])
        CreateAveragePool([1, 1, 1, 1], [3, 3], [3, 3], "NOTSET", [1, 1, 1, 1])
        CreateAveragePool([1, 1, 10, 10], [2, 2], [2, 2], "NOTSET", [1, 1, 1, 1])

        # Test different kernels, strides, no padding
        CreateAveragePool([1, 3, 8, 8], [2, 2], [2, 2])
        CreateAveragePool([1, 3, 9, 9], [3, 3], [3, 3])
        CreateAveragePool([1, 3, 9, 8], [3, 2], [3, 2])
        CreateAveragePool([1, 3, 8, 9], [2, 3], [2, 3])

        # Simple padding example, kernel matches stride
        CreateAveragePool([1, 3, 1, 1], [2, 2], [2, 2], "SAME_UPPER")
        CreateAveragePool([1, 3, 3, 3], [2, 2], [2, 2], "SAME_UPPER")
        CreateAveragePool([1, 3, 5, 5], [2, 2], [2, 2], "SAME_UPPER")

        CreateAveragePool([1, 3, 1, 1], [2, 2], [2, 2], "SAME_LOWER")
        CreateAveragePool([1, 3, 3, 3], [2, 2], [2, 2], "SAME_LOWER")
        CreateAveragePool([1, 3, 5, 5], [2, 2], [2, 2], "SAME_LOWER")

        # Larger size
        CreateAveragePool([1, 3, 8, 8], [3, 2], [2, 3], "SAME_UPPER")
        CreateAveragePool([1, 3, 8, 8], [2, 3], [3, 2], "SAME_UPPER")
        CreateAveragePool([1, 3, 8, 8], [3, 3], [2, 2], "SAME_UPPER")
        CreateAveragePool([1, 3, 8, 8], [2, 2], [3, 3], "SAME_UPPER")
        CreateAveragePool([1, 3, 8, 8], [3, 2], [2, 3], "SAME_LOWER")
        CreateAveragePool([1, 3, 8, 8], [2, 3], [3, 2], "SAME_LOWER")
        CreateAveragePool([1, 3, 8, 8], [3, 3], [2, 2], "SAME_LOWER")
        CreateAveragePool([1, 3, 8, 8], [2, 2], [3, 3], "SAME_LOWER")
        CreateAveragePool([1, 3, 8, 8], [3, 2], [2, 3], "VALID")
        CreateAveragePool([1, 3, 8, 8], [2, 3], [3, 2], "VALID")
        CreateAveragePool([1, 3, 8, 8], [3, 3], [2, 2], "VALID")
        CreateAveragePool([1, 3, 8, 8], [2, 2], [3, 3], "VALID")

        CreateAveragePool([1, 3, 5, 5], [20, 20], [20, 20], "SAME_UPPER")
        CreateAveragePool([1, 3, 5, 5], [30, 20], [20, 30], "SAME_UPPER")
        CreateAveragePool([1, 3, 5, 5], [20, 30], [30, 20], "SAME_UPPER")
        CreateAveragePool([1, 3, 5, 5], [30, 30], [20, 20], "SAME_UPPER")
        CreateAveragePool([1, 3, 5, 5], [20, 20], [30, 30], "SAME_UPPER")

        CreateAveragePool([1, 3, 5, 5], [20, 20], [20, 20], "SAME_LOWER")
        CreateAveragePool([1, 3, 5, 5], [30, 20], [20, 30], "SAME_LOWER")
        CreateAveragePool([1, 3, 5, 5], [20, 30], [30, 20], "SAME_LOWER")
        CreateAveragePool([1, 3, 5, 5], [30, 30], [20, 20], "SAME_LOWER")
        CreateAveragePool([1, 3, 5, 5], [20, 20], [30, 30], "SAME_LOWER")

        # Common example
        CreateAveragePool([1, 3, 32, 32], [2, 2], [2, 2], "VALID")

        CreateAveragePool([1, 64, 8, 8], [8, 8], [8, 8])

        if testBig:
            CreateAveragePool([1, 3, 100, 100], [100, 100], [100, 100], "SAME_LOWER")

        # 4 D - Not supported by runtime, so cannot generate the test

    # Convolution
    if testConv:
        # All padding posibilities, mostly to test the window generation
        # Input shape, features, kernel, stride, dilations, bias
        if generativeTests:
            nP = [1]  # [1, 2] - nocheckin: TODO: Currently batches are broken
            aP = [[3, 3], [5, 5]]
            cP = [1, 3, 4]
            fP = [1, 3, 4]
            kP = [[3, 3], [5, 5]]
            sP = [[3, 3], [5, 5]]
            dP = [[1, 1]]
            bP = [False, True]
            pP = [
                PaddingType("NOTSET", [1, 1, 1, 1]),
                PaddingType("NOTSET", [4, 2, 1, 6]),
                PaddingType("SAME_LOWER"),
                PaddingType("SAME_UPPER"),
            ]

            if testBig:
                aP = [[3, 3], [5, 5]]
                cP = [1, 3, 4, 6, 8, 16]
                fP = [1, 3, 4, 6, 8, 16]
                sP = [[3, 3], [5, 5], [9, 9]]

            # pP = [PaddingType("SAME_LOWER"), PaddingType("SAME_UPPER"), PaddingType("NOTSET",[1,1,1,1])]
            gP = [1, 2, 3, 4, 8]

            args = []
            for n in nP:
                for a in aP:
                    for c in cP:
                        for f in fP:
                            for k in kP:
                                for s in sP:
                                    for d in dP:
                                        for b in bP:
                                            for p in pP:
                                                for g in gP:
                                                    CreateConvolution(
                                                        [n, c, *a],
                                                        f,
                                                        k,
                                                        s,
                                                        d,
                                                        g,
                                                        b,
                                                        p.kind,
                                                        p.padding,
                                                    )

        CreateConvolution([1, 2, 2, 2], 2, [2, 2], [2, 2], [1, 1], 2)
        CreateConvolution([1, 2, 2, 2], 2, [2, 2], [2, 2], [1, 1], 2, True)

        CreateConvolution([1, 4, 2, 2], 4, [2, 2], [2, 2], [1, 1], 1)
        CreateConvolution([1, 4, 2, 2], 4, [2, 2], [2, 2], [1, 1], 2)
        CreateConvolution([1, 4, 2, 2], 4, [2, 2], [2, 2], [1, 1], 4)

        CreateConvolution([1, 4, 2, 2], 4, [2, 2], [2, 2], [1, 1], 1, True)
        CreateConvolution([1, 4, 2, 2], 4, [2, 2], [2, 2], [1, 1], 2, True)
        CreateConvolution([1, 4, 2, 2], 4, [2, 2], [2, 2], [1, 1], 4, True)

        CreateConvolution([1, 2, 2, 2], 2, [2, 2], [2, 2], [1, 1], 2)
        CreateConvolution([1, 4, 2, 2], 2, [2, 2], [2, 2], [1, 1], 2)
        CreateConvolution([1, 4, 4, 4], 2, [2, 2], [2, 2], [1, 1], 2)

        n = 1
        c = 3
        f = 16

        k = [3, 3]
        s = [3, 3]
        d = [1, 1]
        b = False
        p = "NOTSET"
        g = 1

        #                                                  T  L  B  R
        CreateConvolution([n, c, 6, 6], f, k, s, d, g, b, p, [0, 0, 0, 0])

        # TODO: Temporarely disabled while we test the NHWC impl of Conv. Cannot handle padding right now
        if False:
            CreateConvolution([n, c, 5, 6], f, k, s, d, g, b, p, [1, 0, 0, 0])
            CreateConvolution([n, c, 6, 5], f, k, s, d, g, b, p, [0, 1, 0, 0])
            CreateConvolution([n, c, 5, 6], f, k, s, d, g, b, p, [0, 0, 1, 0])
            CreateConvolution([n, c, 6, 5], f, k, s, d, g, b, p, [0, 0, 0, 1])
            CreateConvolution([n, c, 5, 5], f, k, s, d, g, b, p, [1, 1, 0, 0])
            CreateConvolution([n, c, 4, 6], f, k, s, d, g, b, p, [1, 0, 1, 0])
            CreateConvolution([n, c, 5, 5], f, k, s, d, g, b, p, [1, 0, 0, 1])
            CreateConvolution([n, c, 5, 5], f, k, s, d, g, b, p, [0, 1, 1, 0])
            CreateConvolution([n, c, 6, 4], f, k, s, d, g, b, p, [0, 1, 0, 1])
            CreateConvolution([n, c, 5, 5], f, k, s, d, g, b, p, [0, 0, 1, 1])
            CreateConvolution([n, c, 4, 5], f, k, s, d, g, b, p, [1, 1, 1, 0])
            CreateConvolution([n, c, 5, 4], f, k, s, d, g, b, p, [1, 1, 0, 1])
            CreateConvolution([n, c, 4, 5], f, k, s, d, g, b, p, [1, 0, 1, 1])
            CreateConvolution([n, c, 5, 4], f, k, s, d, g, b, p, [0, 1, 1, 1])
            CreateConvolution([n, c, 4, 4], f, k, s, d, g, b, p, [1, 1, 1, 1])
            CreateConvolution([n, c, 1, 1], f, k, s, d, g, b, p, [1, 1, 1, 1])
            CreateConvolution([n, c, 10, 10], f, k, s, d, g, b, p, [1, 1, 1, 1])

        # No padding
        # Different: Input shape, features, kernel, stride, dilations, bias
        CreateConvolution([1, 1, 3, 3], 1, [3, 3], [3, 3], d)
        CreateConvolution([1, 2, 3, 3], 1, [3, 3], [3, 3], d)
        CreateConvolution([1, 1, 3, 3], 2, [3, 3], [3, 3], d)
        CreateConvolution([1, 2, 3, 3], 2, [3, 3], [3, 3], d)

        # Same but in a 2x2 square
        CreateConvolution([1, 1, 6, 6], 1, [3, 3], [3, 3], d)
        CreateConvolution([1, 2, 6, 6], 1, [3, 3], [3, 3], d)
        CreateConvolution([1, 1, 6, 6], 2, [3, 3], [3, 3], d)
        CreateConvolution([1, 2, 6, 6], 2, [3, 3], [3, 3], d)

        # Same but for a 5x5 kernel
        CreateConvolution([1, 1, 5, 5], 1, [5, 5], [5, 5], d)
        CreateConvolution([1, 2, 5, 5], 1, [5, 5], [5, 5], d)
        CreateConvolution([1, 1, 5, 5], 2, [5, 5], [5, 5], d)
        CreateConvolution([1, 2, 5, 5], 2, [5, 5], [5, 5], d)

        # Same but for a 2x2 kernel with stride of 1x1 (result is 3x3)
        CreateConvolution([1, 1, 4, 4], 1, [2, 2], [1, 1], d)
        CreateConvolution([1, 2, 4, 4], 1, [2, 2], [1, 1], d)
        CreateConvolution([1, 1, 4, 4], 2, [2, 2], [1, 1], d)
        CreateConvolution([1, 2, 4, 4], 2, [2, 2], [1, 1], d)

        # Different sized kernels
        CreateConvolution([1, 1, 2, 3], 1, [2, 3], [2, 3], d)
        CreateConvolution([1, 1, 3, 2], 1, [3, 2], [3, 2], d)
        CreateConvolution([1, 1, 4, 9], 1, [2, 3], [2, 3], d)
        CreateConvolution([1, 1, 9, 4], 1, [3, 2], [3, 2], d)

        # Bigger more realistic examples
        CreateConvolution([1, 3, 16, 16], 16, [2, 2], [2, 2], d)

        # Different groups
        # CreateConvolution([1, 2, 4, 4], 1, [2, 2], [1, 1], d, 2)

        # TODO: Temporarely disabled while we test the NHWC impl of Conv. Cannot handle padding right now
        if False:
            CreateConvolution(
                [1, 1, 1, 1], 2, [5, 5], [5, 5], d, g, False, "SAME_UPPER"
            )
            CreateConvolution(
                [1, 1, 1, 1], 2, [5, 5], [1, 1], d, g, False, "SAME_UPPER"
            )
            CreateConvolution(
                [1, 1, 1, 1], 1, [5, 5], [1, 1], d, g, False, "SAME_UPPER"
            )
            CreateConvolution(
                [1, 1, 3, 3], 1, [5, 5], [1, 1], d, g, False, "SAME_UPPER"
            )
            CreateConvolution(
                [1, 1, 5, 5], 1, [5, 5], [1, 1], d, g, False, "SAME_UPPER"
            )
            CreateConvolution(
                [1, 1, 8, 8], 2, [5, 5], [1, 1], d, g, False, "SAME_UPPER"
            )
            CreateConvolution(
                [1, 1, 10, 10], 2, [5, 5], [1, 1], d, g, False, "SAME_UPPER"
            )
            CreateConvolution(
                [1, 1, 15, 15], 2, [5, 5], [1, 1], d, g, False, "SAME_UPPER"
            )
            CreateConvolution(
                [1, 1, 20, 20], 2, [5, 5], [1, 1], d, g, False, "SAME_UPPER"
            )
            CreateConvolution(
                [1, 1, 28, 28], 2, [5, 5], [1, 1], d, g, False, "SAME_UPPER"
            )

        # Adding bias
        CreateConvolution([1, 1, 3, 3], 1, [3, 3], [3, 3], d, g, True)
        CreateConvolution([1, 2, 3, 3], 1, [3, 3], [3, 3], d, g, True)
        CreateConvolution([1, 1, 3, 3], 2, [3, 3], [3, 3], d, g, True)
        CreateConvolution([1, 2, 3, 3], 2, [3, 3], [3, 3], d, g, True)
        CreateConvolution([1, 1, 2, 3], 1, [2, 3], [2, 3], d, g, True)
        CreateConvolution([1, 1, 3, 2], 1, [3, 2], [3, 2], d, g, True)
        CreateConvolution([1, 1, 4, 9], 1, [2, 3], [2, 3], d, g, True)
        CreateConvolution([1, 1, 9, 4], 1, [3, 2], [3, 2], d, g, True)

        if testBig:
            p = PaddingType("NOTSET", [1, 1, 1, 1])
            CreateConvolution(
                [1, 96, 26, 26], 48, [5, 5], [1, 1], [1, 1], 2, True, p.kind, p.padding
            )

            # Does not work
            CreateConvolution(
                [1, 96 // 2, 7, 7],
                48 // 2,
                [5, 5],
                [1, 1],
                [1, 1],
                2,
                True,
                p.kind,
                p.padding,
            )
            CreateConvolution(
                [1, 96 // 2, 5, 5],
                48 // 2,
                [5, 5],
                [1, 1],
                [1, 1],
                2,
                True,
                p.kind,
                p.padding,
            )

    if config.testPad:
        CreatePad([3], [0, 0])
        CreatePad([3], [1, 0])
        CreatePad([3], [0, 1])
        CreatePad([3], [1, 1])
        CreatePad([3], [-1, 0])
        CreatePad([3], [0, -1])
        CreatePad([3], [-1, -1])

        CreatePad([3, 3], [0, 0, 0, 0])
        CreatePad([3, 3], [1, 0, 1, 0])
        CreatePad([3, 3], [0, 1, 0, 1])
        CreatePad([3, 3], [1, 1, 1, 1])
        CreatePad([3, 3], [-1, 0, -1, 0])
        CreatePad([3, 3], [0, -1, 0, -1])
        CreatePad([3, 3], [-1, -1, -1, -1])

        CreatePad([3, 3, 3], [0, 0, 0, 0, 0, 0])
        CreatePad([3, 3, 3], [1, 0, 1, 0, 1, 0])
        CreatePad([3, 3, 3], [0, 1, 0, 1, 0, 1])
        CreatePad([3, 3, 3], [1, 1, 1, 1, 1, 1])
        CreatePad([3, 3, 3], [-1, 0, -1, 0, -1, 0])
        CreatePad([3, 3, 3], [0, -1, 0, -1, 0, -1])
        CreatePad([3, 3, 3], [-1, -1, -1, -1, -1, -1])

        CreatePad([3, 3, 3, 3], [0, 0, 0, 0, 0, 0, 0, 0])
        CreatePad([3, 3, 3, 3], [1, 0, 1, 0, 1, 0, 1, 0])
        CreatePad([3, 3, 3, 3], [0, 1, 0, 1, 0, 1, 0, 1])
        CreatePad([3, 3, 3, 3], [1, 1, 1, 1, 1, 1, 1, 1])
        CreatePad([3, 3, 3, 3], [-1, 0, -1, 0, -1, 0, -1, 0])
        CreatePad([3, 3, 3, 3], [0, -1, 0, -1, 0, -1, 0, -1])
        CreatePad([3, 3, 3, 3], [-1, -1, -1, -1, -1, -1, -1, -1])


def MakeHashable(val):
    if type(val) == list:
        val = tuple(MakeHashable(x) for x in val)
    return val


def OutputFilesFromTestList(outputPath):
    global testList
    global tests

    testList = [x for x in testList if not hasattr(x, "IsValid") or x.IsValid()]

    for i, test in enumerate(testList):
        hashable = {}
        for field in fields(test):
            val = getattr(test, field.name)
            val = MakeHashable(val)
            hashable[field.name] = val

        persistantHash = int(
            hashlib.md5(
                str(hashable).encode("UTF-8"), usedforsecurity=False
            ).hexdigest(),
            16,
        )
        np.random.seed(persistantHash % (2**31))
        test.Create(True)

    allInputNodesAndValuesInOrder = []
    for x in tests:
        for tensor, randomArray in zip(x.tensors, x.randomArrays):
            allInputNodesAndValuesInOrder.append([tensor, randomArray])

    allNodes = []
    for t in tests:
        if isinstance(t.node, list):
            allNodes += t.node
        else:
            allNodes.append(t.node)

    # allNodes = [x.node for x in tests]
    allInputNodes = [x[0] for x in allInputNodesAndValuesInOrder]
    allOutputNodes = [x.outputTensor for x in tests]

    allInitializers = []
    for test in tests:
        if test.initializerArrays:
            for x in test.initializerArrays:
                allInitializers.append(x)

    graph = make_graph(
        allNodes, "simpleTest", allInputNodes, allOutputNodes, allInitializers
    )

    onnx_model = make_model(graph, opset_imports=[make_opsetid("", 7)])
    check_model(onnx_model)
    onnx_model = version_converter.convert_version(onnx_model, 7)
    check_model(onnx_model)
    shaped = onnx.shape_inference.infer_shapes(onnx_model)
    check_model(shaped)

    try:
        shutil.rmtree(outputPath)
    except:
        pass

    try:
        os.makedirs(os.path.join(outputPath, "test_data_set_0"))
    except FileNotFoundError:
        print(f"Error creating path for output: {outputPath}")
        sys.exit(0)
    except FileExistsError:
        pass  # Not a problem if folder already exists.

    for i, nodeAndValue in enumerate(allInputNodesAndValuesInOrder):
        value = nodeAndValue[1]
        with open(os.path.join(outputPath, f"test_data_set_0/input_{i}.pb"), "wb") as f:
            asTensor = numpy_helper.from_array(value)
            f.write(asTensor.SerializeToString())

    sess = ort.InferenceSession(shaped.SerializeToString())

    modelInputs = {}
    for i, test in enumerate(tests):
        for j, randomArray in enumerate(test.randomArrays):
            modelInputs[GetInputTrueName(i, j)] = randomArray

    print(f"Created {len(tests)} subtests")

    modelOutput = sess.run(None, modelInputs)

    for i in range(len(tests)):
        with open(
            os.path.join(outputPath, f"test_data_set_0/output_{i}.pb"), "wb"
        ) as f:
            asTensor = numpy_helper.from_array(modelOutput[i])
            f.write(asTensor.SerializeToString())

    save_onnx_model(shaped, os.path.join(outputPath, "model.onnx"))


def GenerateConvAfterConv():
    global tests
    testIndex = len(tests)

    shape = [1, 1, 1, 1]

    firstKernel = [3, 3]
    secondKernel = [3, 3]

    firstKernelShape = [1, 1, firstKernel[0], firstKernel[1]]
    secondKernelShape = [1, 1, secondKernel[0], secondKernel[1]]

    firstPad = [1, 1, 1, 1]
    secondPad = [1, 1, 1, 1]

    test = Test()

    # First Conv
    firstInputTensor = make_tensor_value_info(
        GetInputTrueName(testIndex, 0), TensorProto.FLOAT, shape
    )

    firstKernelTensor = make_tensor_value_info(
        GetInputTrueName(testIndex, 1), TensorProto.FLOAT, firstKernelShape
    )

    secondKernelTensor = make_tensor_value_info(
        GetInputTrueName(testIndex, 2), TensorProto.FLOAT, secondKernelShape
    )

    firstOutputName = f"TEMP_OUT_CONV_CONV_{testIndex}"
    firstOutputTensor = make_tensor_value_info(
        firstOutputName, TensorProto.FLOAT, [None] * len(shape)
    )
    firstInputs = [GetInputTrueName(testIndex, 0), GetInputTrueName(testIndex, 1)]

    firstNode = make_node(
        "Conv",
        firstInputs,
        [firstOutputName],
        kernel_shape=firstKernel,
        strides=[1, 1],
        dilations=[1, 1],
        group=1,
        auto_pad="NOTSET",
        pads=firstPad,
    )

    secondOutputTensor = make_tensor_value_info(
        GetOutputTrueName(testIndex), TensorProto.FLOAT, [None] * len(shape)
    )

    secondInputs = [firstOutputName, GetInputTrueName(testIndex, 2)]

    secondNode = make_node(
        "Conv",
        secondInputs,
        [GetOutputTrueName(testIndex)],
        kernel_shape=secondKernel,
        strides=[1, 1],
        dilations=[1, 1],
        group=1,
        auto_pad="NOTSET",
        pads=secondPad,
    )

    randomArray0 = np.random.randn(*shape).astype(np.float32)
    randomArray1 = np.random.randn(*firstKernelShape).astype(np.float32)
    randomArray2 = np.random.randn(*secondKernelShape).astype(np.float32)

    test.tensors = [firstInputTensor, firstKernelTensor, secondKernelTensor]
    test.outputTensor = secondOutputTensor
    test.node = [firstNode, secondNode]
    test.randomArrays = [randomArray0, randomArray1, randomArray2]

    tests.append(test)


def GeneratePadAfterConv():
    global tests
    testIndex = len(tests)

    shape = [1, 1, 2, 2]

    firstKernel = [2, 2]
    firstKernelShape = [1, 1, firstKernel[0], firstKernel[1]]
    firstPad = [1, 1, 1, 1]
    strides = [2, 2]

    test = Test()

    # First Conv
    firstInputTensor = make_tensor_value_info(
        GetInputTrueName(testIndex, 0), TensorProto.FLOAT, shape
    )

    firstKernelTensor = make_tensor_value_info(
        GetInputTrueName(testIndex, 1), TensorProto.FLOAT, firstKernelShape
    )

    firstOutputName = f"TEMP_OUT_PAD_CONV_{testIndex}"
    firstOutputTensor = make_tensor_value_info(
        firstOutputName, TensorProto.FLOAT, [None] * len(shape)
    )
    firstInputs = [GetInputTrueName(testIndex, 0), GetInputTrueName(testIndex, 1)]

    firstNode = make_node(
        "Conv",
        firstInputs,
        [firstOutputName],
        kernel_shape=firstKernel,
        strides=strides,
        dilations=[1, 1],
        group=1,
        auto_pad="NOTSET",
        pads=firstPad,
    )

    secondOutputTensor = make_tensor_value_info(
        GetOutputTrueName(testIndex), TensorProto.FLOAT, [None] * len(shape)
    )

    secondInputs = [firstOutputName]

    secondNode = make_node(
        "Pad",
        secondInputs,
        [GetOutputTrueName(testIndex)],
        pads=[0, 0, 2, 2, 0, 0, 4, 4],
    )

    randomArray0 = np.random.randn(*shape).astype(np.float32)
    randomArray1 = np.random.randn(*firstKernelShape).astype(np.float32)

    test.tensors = [firstInputTensor, firstKernelTensor]
    test.outputTensor = secondOutputTensor
    test.node = [firstNode, secondNode]
    test.randomArrays = [randomArray0, randomArray1]

    tests.append(test)


def GeneratePadAfterRelu():
    global tests
    testIndex = len(tests)

    shape = [1, 1, 2, 2]

    test = Test()

    # First Conv
    firstInputTensor = make_tensor_value_info(
        GetInputTrueName(testIndex, 0), TensorProto.FLOAT, shape
    )

    firstOutputName = f"TEMP_OUT_PAD_RELU{testIndex}"
    firstOutputTensor = make_tensor_value_info(
        firstOutputName, TensorProto.FLOAT, [None] * len(shape)
    )
    firstInputs = [GetInputTrueName(testIndex, 0)]

    firstNode = make_node("Relu", firstInputs, [firstOutputName])

    secondOutputTensor = make_tensor_value_info(
        GetOutputTrueName(testIndex), TensorProto.FLOAT, [None] * len(shape)
    )

    secondInputs = [firstOutputName]

    secondNode = make_node(
        "Pad",
        secondInputs,
        [GetOutputTrueName(testIndex)],
        pads=[0, 0, 2, 2, 0, 0, 2, 2],
    )

    randomArray0 = np.random.randn(*shape).astype(np.float32)

    test.tensors = [firstInputTensor]
    test.outputTensor = secondOutputTensor
    test.node = [firstNode, secondNode]
    test.randomArrays = [randomArray0]

    tests.append(test)


def GenerateSoftmax(outputPath):
    config = GenerateTestConfig()
    config.testSoftmax = 1
    GenerateSimpleTest(config)
    OutputFilesFromTestList(outputPath)


def GenerateHeavy(outputPath):
    config = GenerateTestConfig()

    config.testAdd = 1
    config.testRelu = 1
    config.testReshape = 1
    config.testTranspose = 1
    config.testMaxPool = 1
    config.testAveragePool = 1
    config.testMatMul = 1
    config.testDropout = 1
    config.testGemm = 1
    config.testConv = 1
    config.testBatchNormalization = 1
    config.testSoftmax = 1
    config.testLRN = 1
    config.generateOneOfEach = 0
    config.generativeTests = 1
    config.testBig = 1

    GenerateSimpleTest(config)
    OutputFilesFromTestList(outputPath)


def GenerateLite(outputPath):
    config = GenerateTestConfig()
    config.generateOneOfEach = 1
    GenerateSimpleTest(config)
    OutputFilesFromTestList(outputPath)


def GenerateTest(outputPath):
    config = GenerateTestConfig()

    config.testAdd = 1
    config.testRelu = 0
    config.testReshape = 0
    config.testTranspose = 0
    config.testMaxPool = 0
    config.testAveragePool = 0
    config.testMatMul = 0
    config.testDropout = 0
    config.testGemm = 0
    config.testBatchNormalization = 0
    config.testSoftmax = 0
    config.testLRN = 0
    config.testPad = 0

    config.testConv = 1
    config.generateOneOfEach = 1
    config.generativeTests = 0
    config.testBig = 0

    GenerateSimpleTest(config)
    OutputFilesFromTestList(outputPath)


if __name__ == "__main__":
    GenerateTest(sys.argv[1])

# Remember we are currently targetting version=7.
