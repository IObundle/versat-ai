#include "versat_private.h"

#include "stdbool.h"
#include "stdint.h"
#include "stdlib.h" // REMOVE THIS AFTER REMOVING MALLOC AND FREE

#include "versat_accel.h"

#define MIN(A, B) (((A < B) ? (A) : (B)))
#define MAX(A, B) (((A > B) ? (A) : (B)))

typedef union {
  iptr i;
  float f;
} Convertor;

iptr NoConvert(float f) {
  Convertor c = {};
  c.f = f;
  return c.i;
}

// ======================================
// Arena stuff, which we will eventually remove since we do not want to allocate
// memory while performing inference.

unsigned int Align8(unsigned int in) { return ((in + 7) & ~7); }

#define ALIGN(IN, ALIGNMENT) (((IN) + ((ALIGNMENT)-1)) & ~((ALIGNMENT)-1))

void *PushBytes(Arena *arena, int size, int alignment) {
  arena->used = ALIGN(arena->used, alignment);

  int totalSize = Align8(size); // All allocates are 8 byte aligned. Do not
                                // worry about alignment further

  if (arena->used + size >= arena->allocated) {
    for (int i = 0; i < 5; i++) {
      versat_printf("\n\nArena overflow\n\n");
    }
  }

  void *res = (void *)(((char *)arena->mem) + arena->used);
  arena->used += size;

  return res;
}

#define PushType(ARENA, TYPE)                                                  \
  (TYPE *)PushBytes(ARENA, sizeof(TYPE), __alignof__(TYPE))
#define PushArray(ARENA, COUNT, TYPE)                                          \
  (TYPE *)PushBytes(ARENA, (COUNT) * sizeof(TYPE), __alignof__(TYPE))

typedef struct {
  unsigned int firstMarker;
  unsigned int *secondMarkerPtr;
} CanaryHeader;

bool CheckCanary(void *memory, int line) {
  CanaryHeader *asHeader = ((CanaryHeader *)memory) - 1;

  if (asHeader->firstMarker != 0x12345678) {
    versat_printf("Canary check failed before at line: %d value: %08x \n", line,
                  asHeader->firstMarker);
    versat_printf("HeaderPtr: %p FirstMarkerPtr: %p\n", asHeader,
                  &asHeader->firstMarker);
    return false;
  }

  if (*asHeader->secondMarkerPtr != 0x87654321) {
    versat_printf("Canary check failed after at line: %d value: %08x\n", line,
                  *asHeader->secondMarkerPtr);
    versat_printf("SecondMarkerPtr: %p\n", asHeader->secondMarkerPtr);
    return false;
  }

  return true;
}

void *PushBytesWithCanary(Arena *arena, int size) {
  CanaryHeader *header = PushType(arena, CanaryHeader);
  void *memory = PushBytes(arena, size, 1);
  unsigned int *last = PushType(arena, unsigned int);

  header->firstMarker = 0x12345678;
  header->secondMarkerPtr = last;

  *last = 0x87654321;

  // This should never fail, right?
  if (!CheckCanary(memory, -1)) {
    versat_printf("%p %p %p\n", header, memory, last);
  }

  return memory;
}

#define PushTypeWithCanary(ARENA, TYPE)                                        \
  (TYPE *)PushBytesWithCanary(ARENA, sizeof(TYPE))
#define PushArrayWithCanary(ARENA, COUNT, TYPE)                                \
  (TYPE *)PushBytesWithCanary(ARENA, (COUNT) * sizeof(TYPE))

typedef struct {
  Arena *arena;
  int used;
} ArenaMark;

ArenaMark MarkArena(Arena *arena) {
  ArenaMark mark = {};
  mark.arena = arena;
  mark.used = arena->used;
  return mark;
}

void MarkPop(ArenaMark mark) { mark.arena->used = mark.used; }

// TODO: All this memory allocation is very bad. We do not want to allocate
// memory at all, and we would like to push as much memory stuff to the outside
// code. We want memory to be allocated once by the user before calling
Tensor PushTensor(Arena *arena, int64_t *dims, int numberDims) {
  Tensor tensor = CreateTensor_NoAllocate(dims, numberDims);

  int size = 1;
  for (int i = 0; i < numberDims; i++) {
    size *= dims[i];
  }

  tensor.data = PushArrayWithCanary(arena, size, float);
  return tensor;
}

static void Tensor_CheckCanary_(Tensor in, int line) {
  CheckCanary(in.data, line);
}
#define Tensor_CheckCanary(IN) Tensor_CheckCanary_(IN, __LINE__)

Tensor Tensor_Transpose(Tensor input, int *transposeIndex, Arena *arenaOut) {
  int size = input.dims.size;
  int64_t *inDims = input.dims.data;

  int64_t outDims[MAX_DIMS] = {};

  for (int i = 0; i < size; i++) {
    int index = transposeIndex[i];
    outDims[i] = inDims[index];
  }

  Tensor res = PushTensor(arenaOut, outDims, size);

  AddressGen in = StartAddress(inDims, inDims, size);
  AddressGen out = StartAddress(outDims, outDims, size);

  for (; Address_IsValid(&in); Address_Advance(&in)) {
    int inAddr = Address_GetValue(&in);

    for (int i = 0; i < size; i++) {
      int index = transposeIndex[i];
      out.addressVars[i] = in.addressVars[index];
    }

    int outAddr = Address_GetValue(&out);

    res.data[outAddr] = input.data[inAddr];
  }

  return res;
}

Tensor Tensor_ExtractView(Tensor input, int dimIndex, int start, int size,
                          Arena *arenaOut) {
  AddressGen in =
      StartAddress(input.dims.data, input.dims.data, input.dims.size);

  in.offsetAddressVars[dimIndex] = start;
  in.iterationDims[dimIndex] = (int64_t)size;

  Dimensions outDims = input.dims;
  outDims.data[dimIndex] = size;

  Tensor output = PushTensor(arenaOut, outDims.data, outDims.size);
  AddressGen out = StartAddress(outDims.data, outDims.data, outDims.size);

  for (; Address_IsValid(&in); Address_Advance(&in), Address_Advance(&out)) {
    int inIndex = Address_GetValue(&in);
    int outIndex = Address_GetValue(&out);

    output.data[outIndex] = input.data[inIndex];
  }

  return output;
}

static inline int64_t GetDim(int64_t *dimArray, int dimSize, int index) {
  if (index < dimSize) {
    return MAX(dimArray[index], 1);
  }

  return 1;
}

static inline int64_t GetSize(int64_t *dimArray, int dimSize, int index) {
  if (index < dimSize) {
    if (dimArray[index] > 1) {
      return 1;
    }
  }

  return 0;
}

#define SWAP(TYPE, A, B)                                                       \
  do {                                                                         \
    TYPE t = A;                                                                \
    A = B;                                                                     \
    B = t;                                                                     \
  } while (0)

#include <string.h>

void *Versat_Add(void *inputA, void *inputB, void *output, int index,
                 AddInfo *info) {
  int64_t *l = VERSAT_AddInfo_firstInputDims(info);
  int64_t *r = VERSAT_AddInfo_secondInputDims(info);
  int64_t *o = VERSAT_AddInfo_broadCastedShape(info);

  int d = info->maxDims;

  Dimensions left = CreateDimensions(l, d);
  Dimensions right = CreateDimensions(r, d);

  if (Dimensions_TotalSize(left) < Dimensions_TotalSize(right)) {
    SWAP(void *, inputA, inputB);
    SWAP(Dimensions, left, right);
    SWAP(int64_t *, l, r);
  }

  volatile Top_AddConfig *config = &accelConfig->Top_Add;
  ActivateMergedAccelerator(MergeType_Top_Add);

  float *viewA = (float *)inputA;
  float *viewB = (float *)inputB;
  float *out = (float *)output;

  // TODO: Eventually this will depend on the size of Versat memories
  //       The bigger the more efficient we can be
  int maxLineSupported = 1024;

  AddressGen inA = StartAddress(o, l, info->maxDims);
  AddressGen inB = StartAddress(o, r, info->maxDims);
  AddressGen outGen = StartAddress(o, o, info->maxDims);

  int lineLength = l[d - 1];
  while (Address_IsValid(&outGen)) {
    int indexA = Address_GetValue(&inA);
    int indexB = Address_GetValue(&inB);
    int indexO = Address_GetValue(&outGen);

    bool broadcastedB = (GetSize(r, d, d - 1) == 0);

    for (int offset = 0; offset < lineLength; offset += maxLineSupported) {
      int trueLength = MIN(maxLineSupported, lineLength - offset);

      Top_Add_Linear(&viewA[indexA + offset], trueLength);
      Top_Add_Broadcast(&viewB[indexB + (broadcastedB ? 0 : offset)],
                        trueLength, GetSize(r, d, d - 1));
      Top_Add_Output(&out[indexO + offset], trueLength);

      RunAccelerator(1);
    }

    for (int i = 0; i < lineLength; i++) {
      Address_Advance(&inA);
      Address_Advance(&inB);
      Address_Advance(&outGen);
    }
  }

  VERSAT_DisableReadsAndWrites();
  RunAccelerator(2);

  return output;
}

void *Versat_Relu(void *inputA, void *output, int index, ReluInfo *info) {
  volatile Top_ReluConfig *config = &accelConfig->Top_Relu;

  ActivateMergedAccelerator(MergeType_Top_Relu);

  if (inputA == output) {
    // versat_printf("INPLACE RELU\n");
  }

  int64_t *inputDims = VERSAT_ReluInfo_inputDims(info);
  int64_t totalSize = CalculateSizeOfDim(inputDims, info->dims);

#if 0
  VersatVarSpec sizeSpec = {};
  sizeSpec.min = 1;
  sizeSpec.max = totalSize;
  Top_Relu_Simple_Size(&sizeSpec);
#endif

  // TODO: Replace with versat calculated limit
  int64_t maxAtATime = MIN(totalSize, 1024); // sizeSpec.value / 2;

  float *inputView = (float *)inputA;
  float *outputView = (float *)output;

  for (int64_t i = 0; i < totalSize; i += maxAtATime) {
    int size = MIN(maxAtATime, totalSize - i);

    Top_Relu_Simple(&inputView[i], &outputView[i], size);

    // versat_printf("%llx %d\n", i, size);
    RunAccelerator(1);
  }

  VERSAT_DisableReadsAndWrites();
  RunAccelerator(2);

  versat_clearCache(NULL, 0);

  return output;
}

void *Versat_Reshape(void *data, void *shape, void *output, int index,
                     ReshapeInfo *info) {
  int64_t *dims = VERSAT_ReshapeInfo_inputDims(info);

  if (data == shape) {
    // versat_printf("INPLACE RESHAPE\n");
    return data;
  }

  int64_t size = 1;
  for (int64_t i = 0; i < info->numberInputDims; i++) {
    size *= dims[i];
  }

  float *inView = (float *)data;
  float *outView = (float *)output;

  for (int i = 0; i < size; i++) {
    outView[i] = inView[i];
  }

  return data;
}

static inline void MaxPool_ProcessWindow(AdvancedWindow w, int channel,
                                         void *input, void *output,
                                         MaxPoolInfo *info) {
#if 1
  volatile Top_MaxpoolConfig *config = &accelConfig->Top_Maxpool;

  int64_t *inputDims = VERSAT_MaxPoolInfo_inputDims(info);
  int64_t *outputDims = VERSAT_MaxPoolInfo_outputDims(info);
  int *kernelDims = VERSAT_MaxPoolInfo_kernelDims(info);
  int *strideDims = VERSAT_MaxPoolInfo_strideDims(info);
  int *padsDims = VERSAT_MaxPoolInfo_padsDims(info);

  int inputImageW = inputDims[3];
  int inputImageH = inputDims[2];

  int outputImageW = outputDims[3];
  int outputImageH = outputDims[2];

  int cInStart = channel * inputImageH * inputImageW;
  int cOutStart = channel * outputImageH * outputImageW;

  int stride = w.actualKernelW * w.actualKernelH;

  int strideW = strideDims[1];
  int strideH = strideDims[0];

  Top_Maxpool_Features(input, w.inputX, w.inputY, cInStart, w.actualKernelW,
                       w.actualKernelH, inputImageW, w.outputW, w.outputH,
                       strideW, strideH);

  Top_Maxpool_Output(output, w.outputX, w.outputY, cOutStart, w.outputW,
                     w.outputH, outputImageW, stride);

  config->accum.strideMinusOne = stride - 1;
  StartAccelerator();
#endif
}

// Currently hardcoded for 2D kernels.
void *Versat_MaxPool(void *inputX, void *output, int index, MaxPoolInfo *info) {
  // forceDoubleLoop = true;
#if 1
  volatile Top_MaxpoolConfig *config = &accelConfig->Top_Maxpool;
  ActivateMergedAccelerator(MergeType_Top_Maxpool);

  int64_t *inputDims = VERSAT_MaxPoolInfo_inputDims(info);
  int channels = inputDims[1];

  ExtraInfo extra = CalculateExtraInfo_MaxPool(info);

  // MaxPool is currently using NCHW. We iterate by channels since there is no
  // gain in passing a window that spans channels.

  // For MaxPool using NHWC the approach might be different.
  // We might want to use windows that span channels
  for (int c = 0; c < channels; c++) {
    WindowGen genInst = StartWindowGen(&extra, false, false);
    WindowGen *gen = &genInst;

    for (; WindowGen_Valid(gen); WindowGen_Advance(gen)) {
      AdvancedWindow w = WindowGen_Get(gen);
      MaxPool_ProcessWindow(w, c, inputX, output, info);
    }
  }

  VERSAT_DisableReadsAndWrites();
  RunAccelerator(2);

  return output;
#endif
}

static inline void AveragePool_ProcessWindow(AdvancedWindow w, int channel,
                                             void *input, void *output,
                                             AveragePoolInfo *info) {
  volatile Top_AveragePoolConfig *config = &accelConfig->Top_AveragePool;

  int64_t *inputDims = VERSAT_AveragePoolInfo_inputDims(info);
  int64_t *outputDims = VERSAT_AveragePoolInfo_outputDims(info);
  int *kernelDims = VERSAT_AveragePoolInfo_kernelDims(info);
  int *strideDims = VERSAT_AveragePoolInfo_strideDims(info);
  int *padsDims = VERSAT_AveragePoolInfo_padsDims(info);

  int inputImageW = inputDims[3];
  int inputImageH = inputDims[2];

  int outputImageW = outputDims[3];
  int outputImageH = outputDims[2];

  int cInStart = channel * inputImageH * inputImageW;
  int cOutStart = channel * outputImageH * outputImageW;

  int stride = w.actualKernelW * w.actualKernelH;

  int strideW = strideDims[1];
  int strideH = strideDims[0];

  float *asFloat = (float *)output;
  float *correctedOutputStart = asFloat +
                                (channel * outputImageH * outputImageW) +
                                (w.outputY * outputImageW) + w.outputX;

  Top_AveragePool_Features(input, w.inputX, w.inputY, cInStart, w.actualKernelW,
                           w.actualKernelH, inputImageW, w.outputW, w.outputH,
                           strideW, strideH);
  Top_AveragePool_Output(correctedOutputStart, 0, 0, 0, w.outputW, w.outputH,
                         outputImageW, stride);

  config->averagePool_accum.strideMinusOne = stride - 1;
  config->invertedDivisor.constant = NoConvert(1.0f / (float)stride);
  StartAccelerator();
}

// Currently hardcoded for 2D kernels.
void *Versat_AveragePool(void *inputX, void *output, int index,
                         AveragePoolInfo *info) {
  // forceDoubleLoop = true;

  volatile Top_AveragePoolConfig *config = &accelConfig->Top_AveragePool;
  ActivateMergedAccelerator(MergeType_Top_AveragePool);

  int64_t *inputDims = VERSAT_AveragePoolInfo_inputDims(info);

  int channels = inputDims[1];

  ExtraInfo extra = CalculateExtraInfo_AveragePool(info);

  // Using NCHW
  // for (int c = 0; c < channels; c++) {
  WindowGen genInst = StartWindowGen(&extra, true, false);
  WindowGen *gen = &genInst;

  for (; WindowGen_Valid(gen); WindowGen_Advance(gen)) {
    AdvancedWindow w = WindowGen_Get(gen);
    // AdvancedWindow_Print(w);
    AveragePool_ProcessWindow(w, w.outputC, inputX, output, info);
  }
  //}

  VERSAT_DisableReadsAndWrites();
  RunAccelerator(2);

  versat_clearCache(NULL, 0);

  return output;
}

// The reason everything works is because the inputChannels is being divided by
// the group already
//

void ConvWithBias_ProcessWindow(ExtraInfo extra, AdvancedWindow w, void *inputX,
                                void *inputW, void *outAddr, float *bias,
                                ConvInfo *info, int inputC, int outputC,
                                int g) {
  // ProfileScope(1, "Window gen begin");

  volatile Top_ConvConfig *config = &accelConfig->Top_Conv;

  int64_t *inputDims = VERSAT_ConvInfo_inputDims(info);
  int64_t *outputDims = VERSAT_ConvInfo_outputDims(info);
  int *kernelDims = VERSAT_ConvInfo_kernelDims(info);
  int *strideDims = VERSAT_ConvInfo_strideDims(info);

  int inputChannels = inputDims[1];
  int inputImageW = inputDims[3] + extra.padW;

  if (info->isNHWC) {
    inputChannels = inputDims[3];
    inputImageW = inputDims[2] + extra.padW;
  }

  int inputImageC = inputC;
  int outputImageW = outputDims[3];

  if (info->isNHWC) {
    outputImageW = outputDims[2];
  }

  int kernelW = kernelDims[1];
  int kernelH = kernelDims[0];

  int stride = w.actualKernelW * w.actualKernelH * inputImageC;
  int convChannelSize = inputImageC;

  int convStartC = 0; // We must always process the entire input channels.

  int inChannelsPerGroup = inputChannels / info->group;
  int groupOffset = g * inChannelsPerGroup;

  // ProfileScope(1, "Before main init function");
  Top_Conv_FeaturesWeightsOutputs(
      inputX, inputW, outAddr, w.actualKernelW, w.actualKernelH,
      convChannelSize,

      w.outputH, w.outputW, w.outputSizeC,

      w.inputX, w.inputY, w.kernelStartW, w.kernelStartH, w.startC, w.outputX,
      w.outputY,

      inputImageW, inputImageC, convStartC, kernelW, kernelH,

      outputImageW, stride, outputC,

      strideDims[1], strideDims[0]);
  // ProfileScope(1, "After main init function");

  if (bias == NULL) {
    static float bias = 0.0f;
    Top_Conv_Bias(&bias, 1, 1, w.outputW, w.outputH, w.actualKernelH,
                  w.actualKernelW, inputImageC);
  } else {
    Top_Conv_Bias(bias + w.startC, w.outputSizeC, stride, w.outputW, w.outputH,
                  w.actualKernelH, w.actualKernelW, inputImageC);
  }

  // ProfileScope(1,"Gonna start accel");
  StartAccelerator();
  // ProfileScope(1, "Window gen end");
}

void *Versat_Conv(void *inputX, void *inputW, void *output, int index,
                  ConvInfo *info) {
  Versat_ConvWithBias(inputX, inputW, NULL, output, index, info);
}

static bool PowerOf2(int val) {
  if (val == 0) {
    return false;
  }

  if ((val & (val - 1)) == 0) {
    return true;
  }

  return false;
}

void *Versat_ConvWithBias(void *inputX, void *inputW, void *inputB,
                          void *output, int index, ConvInfo *info) {
  ProfileScope(0, "Start Of Conv");

  volatile Top_ConvConfig *config = &accelConfig->Top_Conv;

  int64_t *inputDims = VERSAT_ConvInfo_inputDims(info);
  int64_t *outputDims = VERSAT_ConvInfo_outputDims(info);
  int *kernelDims = VERSAT_ConvInfo_kernelDims(info);
  int *strideDims = VERSAT_ConvInfo_strideDims(info);
  int *padsDims = VERSAT_ConvInfo_padsDims(info);

  ArenaMark outerMark = MarkArena(arena);

  ActivateMergedAccelerator(MergeType_Top_Conv);

  ProfileScope(0, "After merge activate");

  int batches = inputDims[0];
  int inputChannels = inputDims[1];
  int inputImageH = inputDims[2];
  int inputImageW = inputDims[3];

  if (info->isNHWC) {
    inputChannels = inputDims[3];
    inputImageH = inputDims[1];
    inputImageW = inputDims[2];
  }

  int outputChannels = outputDims[1];
  int outputImageH = outputDims[2];
  int outputImageW = outputDims[3];

  if (info->isNHWC) {
    outputChannels = outputDims[3];
    outputImageH = outputDims[1];
    outputImageW = outputDims[2];
  }

  int inputSize = inputImageW * inputImageH * inputChannels;
  int outputSize = outputImageW * outputImageH * outputChannels;
  int group = info->group;

  Tensor fullOutput = PushTensor(arena, outputDims, 4);
  float *properOutput = fullOutput.data;

  // For group == 1 we can just write directly
  if (info->isNHWC && group == 1) {
    properOutput = (float *)output;
  }

  int kernelW = kernelDims[1];
  int kernelH = kernelDims[0];

  VersatVarSpec outputCSpec = {1, (outputChannels / group), 0};
  VersatVarSpec outputWSpec = {1, outputImageW, 1};
  VersatVarSpec outputHSpec = {1, outputImageH, 2};

  // We calculate size based the size of the kernel, the amount of input
  // channels and the value of the outputs.
  int bytesUsed = Top_Conv_FeaturesWeightsOutputs_Size(
      kernelW, kernelH, inputChannels, &outputHSpec, &outputWSpec,
      &outputCSpec);

  ProfileScope(0, "After size calculations");

  Tensor inputTensor = CreateTensor_NoAllocate(inputDims, 4);
  inputTensor.data = inputX;

  // Currently we divide on batches but for small convolutions we might need to
  // be able to support this.
  for (int batch = 0; batch < batches; batch++) {
    ProfileScope(0, "Start batch loop");

    ArenaMark mark = MarkArena(arena);

    // TODO: This technically depends on batch because we have group related
    // operations that change these values.
    // If we remove them we can then push this outside the loop
    ExtraInfo extra = CalculateExtraInfo_Conv(info);

    float *inputView = (float *)inputX;
    inputView += batch * inputSize;

    ProfileScope(0, "After calculate extra info");

    int64_t imageWithPadH = inputImageH + extra.padH;
    int64_t imageWithPadW = inputImageW + extra.padW;

    int64_t NHWCDims[] = {batches, imageWithPadH, imageWithPadW, inputChannels};

    Tensor tempInputTensor = {};
    float *tempInput = NULL;
    if (info->isNHWC) {
      tempInputTensor = CreateTensor_NoAllocate(NHWCDims, 4);
      tempInputTensor.data = inputView;
      tempInput = tempInputTensor.data;
    } else {
      tempInputTensor = PushTensor(arena, NHWCDims, 4);
      tempInput = tempInputTensor.data;
    }

    int kernelSmallSize = kernelDims[1] * kernelDims[0];

    ProfileScope(0, "After tensor pushes");

    int totalInputImageH = inputImageH + extra.rightPadH;
    int totalInputImageW = inputImageW + extra.rightPadW;

    if (info->isNHWC) {
      tempInput = inputView;
    } else {
      // Convert NCHW to NHWC while also adding padding if needed.
      ProfileScope(0, "Before NCHW conversion");
      for (int y = -extra.leftPadH; y < totalInputImageH; y++) {
        for (int x = -extra.leftPadW; x < totalInputImageW; x++) {
          for (int c = 0; c < inputChannels; c++) {
            int NCHW_Index =
                c * (inputImageH * inputImageW) + y * inputImageW + x;
            int NHWC_Index =
                (y + extra.leftPadH) * (imageWithPadW * inputChannels) +
                (x + extra.leftPadW) * inputChannels + c;

            if (y < 0 || y >= inputImageH) {
              tempInput[NHWC_Index] = 0.0f;
              continue;
            }
            if (x < 0 || x >= inputImageW) {
              tempInput[NHWC_Index] = 0.0f;
              continue;
            }

            tempInput[NHWC_Index] = inputView[NCHW_Index];
          }
        }
      }
      ProfileScope(0, "After NCHW conversion");
    }

    int outChannelsPerGroup = outputChannels / group;

    // TODO: Changing extra is kinda "problematic". We are doing a bunch of
    // stuff that might not be needed anymore.
    //       It might be possible to just push this logic to Versat and let it
    //       handle it.
    extra.inputImageC /= group;
    extra.outputImageC /= group;

    int index = 0;
    for (int g = 0; g < group; g++) {
      int inputC = extra.inputImageC;
      int outputC = extra.outputImageC;

      // We extract the input associated to the current group since Versat
      // cannot handle any more loops. For group == 1 we do not need to do this.
      Tensor extracted = {};
      float *properInput = tempInputTensor.data;

      if (group != 1 || !info->isNHWC) {
        extracted =
            Tensor_ExtractView(tempInputTensor, 3, g * inputC, inputC, arena);
        properInput = extracted.data;
      }

      WindowGen genInst =
          StartAdvancedWindowGen(&extra, true, false, outputWSpec.value,
                                 outputHSpec.value, outputCSpec.value);
      WindowGen *gen = &genInst;

      // We extract the bias input.
      float *trueBias = (float *)inputB;
      if (trueBias != NULL) {
        trueBias += (g * extra.outputImageC);
      }

#if 1
      ProfileScope(0, "Before window gen");
      int amountOfWindows = 0;
      AdvancedWindow w = {};
      for (; WindowGen_Valid(gen); WindowGen_AdvanceTruePadding(gen, w)) {
        WindowGen_GetTruePadding(gen, &w);
        amountOfWindows += 1;

        ConvWithBias_ProcessWindow(
            extra, w, properInput,
            ((float *)inputW) +
                g * (kernelSmallSize * (outputChannels / group) *
                     (inputChannels / group)),
            &properOutput[index], trueBias, info, inputC, outputC, g);
      }
#endif

      index += outChannelsPerGroup * outputImageH * outputImageW;

      if (group != 1 || !info->isNHWC) {
        Tensor_CheckCanary(extracted);
      }
    }

    MarkPop(mark);
    ProfileScope(0, "End of batch function");
  }

  // For group == 1 we can just write directly
  if (!info->isNHWC || group != 1) {
    Tensor_CheckCanary(fullOutput);
  }

  VERSAT_DisableReadsAndWrites();
  RunAccelerator(2);

  versat_clearCache(NULL, 0);

  float *outputView = (float *)output;

#if 1
  // Convert back into NCHW if using groups
  if (!info->isNHWC) {
    int cOutSize = outputChannels / group;
    int totalSizePerGroup = cOutSize * outputImageH * outputImageW;

    int index = 0;
    for (int g = 0; g < group; g++) {
      float *groupData = fullOutput.data + (totalSizePerGroup * g);

      for (int c = 0; c < cOutSize; c++) {
        for (int y = 0; y < outputImageH; y++) {
          for (int x = 0; x < outputImageW; x++) {
            int NHWC_Index = y * (cOutSize * outputImageW) + x * cOutSize + c;
            int outIndex = index;

            // versat_printf("%d\n",outIndex);
            outputView[outIndex] = groupData[NHWC_Index];
            index += 1;
          }
        }
      }
    }
  } else if (group != 1) {
    int cOutSize = outputChannels / group;
    int totalSizePerGroup = cOutSize * outputImageH * outputImageW;

    for (int g = 0; g < group; g++) {
      float *groupData = fullOutput.data + (totalSizePerGroup * g);

      for (int y = 0; y < outputImageH; y++) {
        for (int x = 0; x < outputImageW; x++) {
          for (int c = 0; c < cOutSize; c++) {
            int NHWC_Index = y * (cOutSize * outputImageW) + x * cOutSize + c;
            int outIndex = y * (outputImageW * outputChannels) +
                           x * outputChannels + c + (g * cOutSize);

            // versat_printf("%d\n",outIndex);
            outputView[outIndex] = groupData[NHWC_Index];
            index += 1;
          }
        }
      }
    }
  }
#endif

  MarkPop(outerMark);

  ProfileScope(0, "End Of Conv");

  return output;
}

void *Versat_MatMul(void *inputA, void *inputB, void *output, int index,
                    MatMulInfo *info) {
  ArenaMark outerMark = MarkArena(arena);

  ActivateMergedAccelerator(MergeType_Top_MatMul);
  volatile Top_MatMulConfig *config = &accelConfig->Top_MatMul;

  int64_t *inputADims = VERSAT_MatMulInfo_inputADims(info);
  int64_t *inputBDims = VERSAT_MatMulInfo_inputBDims(info);
  int64_t *outputDims = VERSAT_MatMulInfo_outputDims(info);

  float *viewA = (float *)inputA;
  float *viewB = (float *)inputB;
  float *viewOut = (float *)output;

  // TODO: The names are kinda wrong. AH and AW are "technically" swapped in
  // name only.
  int AS = info->numberInputADims;
  int AH;
  int AW;
  if (AS == 1) {
    AH = 1;
    AW = inputADims[0];
  } else {
    AH = inputADims[AS - 2];
    AW = inputADims[AS - 1];
  }

  int BS = info->numberInputBDims;
  int BH;
  int BW;
  if (BS == 1) {
    BH = 1;
    BW = inputBDims[0];
  } else {
    BH = inputBDims[BS - 2];
    BW = inputBDims[BS - 1];
  }

#if 0
  if (info->isBTransposed) {
    int temp = BW;
    BW = BH;
    BH = temp;
  }
#endif

  int totalBSize = BH * BW;
  float *tempB = viewB;

  if (!info->isBTransposed) {
    tempB = PushArray(arena, totalBSize, float);
  }

  if (info->isBTransposed) {
    // versat_printf("MatMul  with transposed\n");
  }

  int OS = info->numberOutputDims;
  int OH;
  int OW;
  if (OS == 1) {
    OH = 1;
    OW = outputDims[0];
  } else {
    OH = outputDims[OS - 2];
    OW = outputDims[OS - 1];
  }

  if (AW != BH) {
    versat_printf("Something very wrong is happening in MatMul\n");
  }

  Dimensions dimA = CreateDimensions(inputADims, info->numberInputADims);
  Dimensions dimB = CreateDimensions(inputBDims, info->numberInputBDims);
  Dimensions dimO = CreateDimensions(outputDims, info->numberOutputDims);

  if (dimA.size == 1) {
    Dimensions_PrependInPlace(&dimA, 1);
  }
  if (dimB.size == 1) {
    Dimensions_PrependInPlace(&dimB, 1);
  }
  if (dimO.size == 1) {
    Dimensions_PrependInPlace(&dimO, 1);
  }

  // NOTE: All this stuff is to handle the upper dims. (3 or more)
  //       For 2 dims the address loop never triggers.
  int dimsToPreserve = 2;
  int dimsToIterateA = MAX(0, dimA.size - dimsToPreserve);
  int dimsToIterateB = MAX(0, dimB.size - dimsToPreserve);
  int dimsToIterateO = MAX(0, dimO.size - dimsToPreserve);

  AddressGen addrA = StartAddressFromDims(dimA, dimsToIterateA);
  AddressGen addrB = StartAddressFromDims(dimB, dimsToIterateB);
  AddressGen addrO = StartAddressFromDims(dimO, dimsToIterateO);

  VersatVarSpec lineSpec = {1, OW, 0};
  Top_MatMul_Simple_Size(AW, &lineSpec);

  while (Address_IsValid(&addrA) || Address_IsValid(&addrB) ||
         Address_IsValid(&addrO)) {
    if (!Address_IsValid(&addrA)) {
      Address_Restart(&addrA);
    }
    if (!Address_IsValid(&addrB)) {
      Address_Restart(&addrB);
    }
    if (!Address_IsValid(&addrO)) {
      Address_Restart(&addrO);
    }

    int valA = Address_GetValue(&addrA);
    int valB = Address_GetValue(&addrB);
    int valO = Address_GetValue(&addrO);

    EndAccelerator();
    float *dataSource = tempB;
    if (!info->isBTransposed) {
      for (int y = 0; y < BH; y++) {
        for (int x = 0; x < BW; x++) {
          // Transposing B
          tempB[x * BH + y] = viewB[y * BW + x + valB];
        }
      }
    }
    if (info->isBTransposed) {
      dataSource = viewB; //&tempB[valB * BH];
    }

    silent_clear_cache();

    int rightLinesToProcess = 24;
    for (int y = 0; y < OH; y++) {
      for (int x = 0; x < OW; x += rightLinesToProcess) {
        int trueLines = MIN(rightLinesToProcess, OW - x);

        float *lineAStart = &viewA[y * AW + valA];
        float *lineBStart = &dataSource[x * AW];

        float *out = &viewOut[y * OW + x + valO];

        Top_MatMul_Simple(lineAStart, lineBStart, AW, trueLines);
        Top_MatMul_Output(out, trueLines, AW);

        config->myAccum.strideMinusOne = AW - 1;

        StartAccelerator();
      }
    }

    Address_Advance(&addrA);
    Address_Advance(&addrB);
    Address_Advance(&addrO);
  }

  VERSAT_DisableReadsAndWrites();
  RunAccelerator(2);

  MarkPop(outerMark);

  return output;
}

void *Versat_Softmax(void *input, void *output, int index, SoftmaxInfo *info) {
  float *view = (float *)input;
  float *out = (float *)output;

  ResetAccelerator();
  ActivateMergedAccelerator(MergeType_Top_Exp);

  int64_t *inputDims = VERSAT_SoftmaxInfo_inputDims(info);

  Top_Exp_LoadExp(expTable, EXP_TABLE_SIZE);
  Top_Exp_LoadFrac(expMantissaTable, EXP_MANTISSA_TABLE_SIZE);

  int64_t size = CalculateSizeOfDim(inputDims, info->numberInputDims);

  VersatVarSpec width = {};
  width.min = 1;
  width.max = MIN(size, 256); // [7]
  Top_Exp_Simple_Size(&width);
  int increment = width.value;

  int axis = info->axis;
  if (axis < 0) {
    axis += info->numberInputDims;
  }

  AddressGen testInst =
      StartAddress(inputDims, inputDims, info->numberInputDims);
  AddressGen *test = &testInst;

  int kernelSize = info->numberInputDims - axis;

  for (int i = 0; i < size; i += increment) {
    int transferSize = MIN(size - i, increment);

    Top_Exp_Simple(&view[i], &out[i], transferSize);
    RunAccelerator(1);
  }

  VERSAT_DisableReadsAndWrites();
  RunAccelerator(2);

  silent_clear_cache();

  int maxIndex = 0;
  for (; Address_IsValid(test); Address_AdvanceAxis(test, axis - 1)) {
    int kernelDims[MAX_DIMS] = {};
    for (int i = 0; i < kernelSize; i++) {
      kernelDims[i] = inputDims[i + axis];
    }

    float sum = 0.0f;

    KernelGen genInst = StartKernel(test, kernelDims, kernelSize);
    KernelGen *gen = &genInst;
    for (; Kernel_IsValid(gen); Kernel_Advance(gen)) {
      int index = Kernel_GetValue(gen);

      maxIndex = MAX(index, maxIndex);

      sum += out[index];
    }

    float invSum = 1.0 / sum;

    genInst = StartKernel(test, kernelDims, kernelSize);
    for (; Kernel_IsValid(gen); Kernel_Advance(gen)) {
      int index = Kernel_GetValue(gen);

      maxIndex = MAX(index, maxIndex);

      out[index] = out[index] * invSum;
    }
  }

  return output;
}

void *Versat_BatchNormalization(void *inputX, void *scale, void *inputB,
                                void *mean, void *var, void *output, int index,
                                BatchNormalizationInfo *info) {
#if 1
  ArenaMark outerMark = MarkArena(arena);

  ActivateMergedAccelerator(MergeType_Top_BatchNormalization);

  int64_t *inputDims = VERSAT_BatchNormalizationInfo_inputDims(info);

  float *x = (float *)inputX;
  float *s = (float *)scale;
  float *b = (float *)inputB;
  float *m = (float *)mean;
  float *v = (float *)var;
  float *o = (float *)output;

  Dimensions dim = CreateDimensions(inputDims, info->numberInputDims);

  if (dim.size <= 1) {
    Dimensions_AppendInPlace(&dim, 1);
  }

  int totalC = dim.data[1];

  float *A = PushArray(arena, totalC, float);
  float *B = PushArray(arena, totalC, float);
  for (int c = 0; c < totalC; c++) {
    float inv = my_invsqrt(v[c] + info->epsilon);
    A[c] = s[c] * inv;
    B[c] = (-m[c] * inv) * s[c] + b[c];
  }

  AddressGen addrInst = StartAddressFromDims(dim, 2);
  AddressGen *addr = &addrInst;

  // TODO: We probably can also do this using the Kernel stuff.
  //       But I kinda want a better interface when using kernel stuff.
  Dimensions leftover = Dimensions_Cut_GetRight(dim, 2);
  int size = Dimensions_TotalSize(leftover);

  VersatVarSpec sizeSpec;
  sizeSpec.min = 1;
  sizeSpec.max = size;
  int bytesTransferPerRun = Top_BatchNormalization_Simple_Size(&sizeSpec);

  int transferSize = sizeSpec.value;

  silent_clear_cache();

  while (Address_IsValid(addr)) {
    int c = Address_GetDim(addr, 1);

    int index = Address_GetValue(addr);

    union {
      int i;
      float f;
    } a, b;

    a.f = A[c];
    b.f = B[c];

    for (int i = 0; i < size; i += transferSize) {
      int trueSize = MIN(size - i, transferSize);
      Top_BatchNormalization_Simple(x, o, index + i, trueSize, a.i, b.i);
      StartAccelerator();
    }

    Address_Advance(addr);
  }

  EndAccelerator();

  VERSAT_DisableReadsAndWrites();
  RunAccelerator(2);

  MarkPop(outerMark);

  return o;
#endif
}

void *Versat_Dropout(void *input, void *out, int index, DropoutInfo *info) {
  int64_t *inputDims = VERSAT_DropoutInfo_inputDims(info);
  Tensor asTensor = CreateTensor_NoAllocate(inputDims, info->numberInputDims);
  int size = Tensor_Size(asTensor);

  float *asFloatIn = (float *)input;
  float *asFloatOut = (float *)out;

  for (int i = 0; i < size; i++) {
    asFloatOut[i] = asFloatIn[i];
  }

  return input;
}

void *Versat_LRN(void *input, void *out, int index, LRNInfo *info) {
#if 1
  ArenaMark outerMark = MarkArena(arena);

  int64_t *inputDims = VERSAT_LRNInfo_inputDims(info);

  int N = inputDims[0];
  int C = inputDims[1];
  int H = inputDims[2];
  int W = inputDims[3];

  int n = info->size;
  float k = info->bias;
  float a = info->alpha;
  float b = info->beta;

  float aDivSize = a / ((float)n);

  float *in = (float *)input;
  float *output = (float *)out;

  int64_t NHWCDims[] = {inputDims[0], inputDims[2], inputDims[3], inputDims[1]};

  Tensor tempInputTensor = PushTensor(arena, NHWCDims, 4);
  float *tempInput = tempInputTensor.data;

  Tensor tempOutputTensor = PushTensor(arena, NHWCDims, 4);
  float *tempOutput = tempOutputTensor.data;

  // Convert NCHW to NHWC
  for (int y = 0; y < H; y++) {
    for (int x = 0; x < W; x++) {
      for (int c = 0; c < C; c++) {
        int NCHW_Index = c * (H * W) + y * W + x;
        int NHWC_Index = y * (W * C) + x * C + c;

        tempInput[NHWC_Index] = in[NCHW_Index];
      }
    }
  }

  ActivateMergedAccelerator(MergeType_Top_LRN);

  Top_LRN_LoadMantissa(logMantissaTable, LOG_MANTISSA_TABLE_SIZE);
  Top_LRN_LoadExp(expTable, EXP_TABLE_SIZE);
  Top_LRN_LoadFrac(expMantissaTable, EXP_MANTISSA_TABLE_SIZE);
  Top_LRN_InitConsts(VERSAT_CONVERT(aDivSize, uint32_t),
                     VERSAT_CONVERT(b, uint32_t), VERSAT_CONVERT(k, uint32_t),
                     log2Val);

  int64_t size = CalculateSizeOfDim(inputDims, 4);
  float *buffer = PushArray(arena, size, float);

  AddressGen addrInst = StartAddress(NHWCDims, NHWCDims, info->numberInputDims);
  AddressGen *addr = &addrInst;
  for (; Address_IsValid(addr); Address_Advance(addr)) {
    int y = Address_GetDim(addr, 1);
    int x = Address_GetDim(addr, 2);
    int c = Address_GetDim(addr, 3);

    int lowerBound = MAX(0, c - n / 2);
    int upperBound = MIN(C - 1, c + n / 2);

    int index = Address_GetValue(addr);

    int yx = y * W * C + x * C;

    Top_LRN_Simple(&tempInput[yx], &buffer[index], lowerBound,
                   upperBound + 1 - lowerBound);
    StartAccelerator();
  }

  VERSAT_DisableReadsAndWrites();
  RunAccelerator(2);

  for (int i = 0; i < size; i++) {
    tempOutput[i] = tempInput[i] / buffer[i];
  }

  // Convert NHWC to NCHW
  for (int y = 0; y < H; y++) {
    for (int x = 0; x < W; x++) {
      for (int c = 0; c < C; c++) {
        int NCHW_Index = c * (H * W) + y * W + x;
        int NHWC_Index = y * (W * C) + x * C + c;

        output[NCHW_Index] = tempOutput[NHWC_Index];
      }
    }
  }

  MarkPop(outerMark);

  return output;
#endif
}

void *Versat_Gemm(void *inA, void *inB, void *inC, void *out, int index,
                  GemmInfo *info) {
#if 1
  ArenaMark outerMark = MarkArena(arena);

  ActivateMergedAccelerator(MergeType_Top_Gemm);
  volatile Top_GemmConfig *config = &accelConfig->Top_Gemm;

  int64_t *aDims = VERSAT_GemmInfo_aDims(info);
  int64_t *bDims = VERSAT_GemmInfo_bDims(info);
  int64_t *cDims = VERSAT_GemmInfo_cDims(info);

  float *viewA = (float *)inA;
  float *viewB = (float *)inB;
  float *viewC = (float *)inC;
  float *viewOut = (float *)out;

  int AH = aDims[0]; // 1
  int AW = aDims[1]; // 4

  int BH = bDims[0];
  int BW = bDims[1];

  int CH = cDims[0];
  int CW = cDims[1];

  int trueAW = AW;
  int trueAH = AH;
  if (info->transA) {
    trueAW = AH;
    trueAH = AW;
  }

  // Since we only allocate one line no point in trying to simplify the
  // allocation
  float *tempA = PushArray(arena, AH, float);

  int trueBW = BW;
  int trueBH = BH;
  if (info->transB) {
    trueBW = BH;
    trueBH = BW;
  }

  int OH = trueAH;
  int OW = trueBW;

  int broadCastH = (OH == CH && OH != 1) ? 1 : 0;
  int broadCastW = (OW == CW && OW != 1) ? 1 : 0;

  int64_t dimsOut[2] = {OH, OW};
#if 0
  Dimensions dimA = CreateDimensions(aDims, info->numberInputDims);
  Dimensions dimB = CreateDimensions(bDims, info->numberInputDims);
  Dimensions dimC = CreateDimensions(cDims, info->numberInputDims);

  Dimensions dimO = CreateDimensions(dimsOut, info->numberInputDims);

  AddressGen addrA = StartAddressFromDims(dimA, 0);
  AddressGen addrB = StartAddressFromDims(dimB, 0);
  AddressGen addrO = StartAddressFromDims(dimO, 0);
#endif

  int valA = 0;
  int valB = 0;
  int valO = 0;

  // By default we transpose B in order to implement the multiplication phase
  // directly. Which means that we do the opposite when we want to "transpose"
  // B.

  float *properBInput = viewB;
  if (!info->transB) {
    int totalBSize = BH * BW;
    float *tempB = PushArray(arena, totalBSize, float);

    for (int y = 0; y < BH; y++) {
      for (int x = 0; x < BW; x++) {
        // Transposing B
        tempB[x * BH + y] = viewB[y * BW + x + valB];
      }
    }

    properBInput = tempB;
  }

  Top_Gemm_Alpha(NoConvert(info->alpha));

  for (int y = 0; y < OH; y++) {
    float *properAInput = &viewA[y * AW];
    if (info->transA) {
      for (int x = 0; x < AH; x++) {
        // Transposing A
        tempA[x] = viewA[x * AW + y];
      }
      properAInput = tempA;
    }

    silent_clear_cache();

    for (int x = 0; x < OW; x++) {
      float *lineAStart = properAInput;
      float *lineBStart = &properBInput[x * trueAW];

      float *out = &viewOut[y * OW + x + valO];

      int cIndex = y * (broadCastH ? CW : 0) + x * (broadCastW ? 1 : 0);

      float cVal = viewC[cIndex];

      Top_Gemm_CValue(NoConvert(cVal * info->beta));

      Top_Gemm_Simple(lineAStart, lineBStart, trueAW);
      Top_Gemm_Output(out, 1, trueAW);

      config->myAccum.strideMinusOne = trueAW - 1;

      StartAccelerator();

      silent_clear_cache();
    }
  }

  VERSAT_DisableReadsAndWrites();
  RunAccelerator(2);

  MarkPop(outerMark);

  return viewOut;
#endif
}
