#include "versat_private.h"

#include "stdbool.h"
#include "stdint.h"
#include "stdlib.h" // REMOVE THIS AFTER REMOVING MALLOC AND FREE

#include "versat_accel.h"

#define MIN(A, B) (((A < B) ? (A) : (B)))
#define MAX(A, B) (((A > B) ? (A) : (B)))

void silent_clear_cache();

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

typedef struct Arena_t {
  void *mem;
  int used;
  int allocated;
} Arena;

void *PushBytes(Arena *arena, int size) {
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

#define PushType(ARENA, TYPE) (TYPE *)PushBytes(ARENA, sizeof(TYPE))
#define PushArray(ARENA, COUNT, TYPE)                                          \
  (TYPE *)PushBytes(ARENA, (COUNT) * sizeof(TYPE))

typedef struct {
  unsigned int firstMarker;
  unsigned int *secondMarkerPtr;
} CanaryHeader;

void CheckCanary(void *memory) {
  CanaryHeader *asHeader = (CanaryHeader *)memory;
  asHeader -= 1;

  if (asHeader->firstMarker != 0x12345678) {
    versat_printf("Canary check failed before allocation\n");
  }

  if (*asHeader->secondMarkerPtr != 0x87654321) {
    versat_printf("Canary check failed after allocation\n");
  }
}

void *PushBytesWithCanary(Arena *arena, int size) {
  CanaryHeader *header = PushType(arena, CanaryHeader);
  void *memory = PushBytes(arena, size);
  unsigned int *last = PushType(arena, unsigned int);

  header->firstMarker = 0x12345678;
  header->secondMarkerPtr = last;

  *last = 0x87654321;

  CheckCanary(memory);

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

static void Tensor_CheckCanary(Tensor in) { CheckCanary(in.data); }

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

void *Versat_Add(void *inputA, void *inputB, void *output, int index,
                 AddInfo *info) {
  int64_t *l = info->firstInputDim;
  int64_t *r = info->secondInputDim;
  int64_t *o = info->broadCastedShape;
  int d = info->maxDims;

  Dimensions left = CreateDimensions(l, d);
  Dimensions right = CreateDimensions(r, d);

  if (Dimensions_Size(left) < Dimensions_Size(right)) {
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

      Linear_VRead(&config->inputs_0, &viewA[indexA + offset], trueLength);
      Broadcast1_VRead(&config->inputs_1,
                       &viewB[indexB + (broadcastedB ? 0 : offset)], trueLength,
                       GetSize(r, d, d - 1));
      Linear_VWrite(&config->output, &out[indexO + offset], trueLength);

      RunAccelerator(1);
    }

    for (int i = 0; i < lineLength; i++) {
      Address_Advance(&inA);
      Address_Advance(&inB);
      Address_Advance(&outGen);
    }
  }

  config->inputs_0.enabled = 0;
  config->inputs_1.enabled = 0;
  config->output.enabled = 0;
  RunAccelerator(2);

  return output;
}

void *Versat_Relu(void *inputA, void *output, int index, ReluInfo *info) {
  volatile Top_ReluConfig *config = &accelConfig->Top_Relu;
  ActivateMergedAccelerator(MergeType_Top_Relu);

  int dims = info->dims;
  int64_t *dim = info->inputDims;

  int64_t totalSize = CalculateSizeOfDim(dim, dims);

  int64_t maxAtATime = 256;

  float *inputView = (float *)inputA;
  float *outputView = (float *)output;

  for (int i = 0; i < totalSize; i += maxAtATime) {
    int size = MIN(maxAtATime, totalSize - i);

    Linear_VRead(&config->input, &inputView[i], size);
    Linear_VWrite(&config->output, &outputView[i], size);

    RunAccelerator(1);
  }

  config->input.enabled = 0;
  config->output.enabled = 0;
  RunAccelerator(2);

  return output;
}

void *Versat_Reshape(void *data, void *shape, void *output, int index,
                     ReshapeInfo *info) {
  return data;
}

static inline void MaxPool_ProcessWindow(AdvancedWindow w, int channel,
                                         void *input, void *output,
                                         MaxPoolInfo *info) {
  volatile Top_MaxpoolConfig *config = &accelConfig->Top_Maxpool;

  int inputImageW = info->inputDims[3];
  int inputImageH = info->inputDims[2];

  int outputImageW = info->outputDims[3];
  int outputImageH = info->outputDims[2];

  int cInStart = channel * inputImageH * inputImageW;
  int cOutStart = channel * outputImageH * outputImageW;

  int stride = w.actualKernelW * w.actualKernelH;

  int strideW = info->strideDims[1];
  int strideH = info->strideDims[0];

  MaxPool2D_VRead(&config->features, input, w.inputX, w.inputY, cInStart,
                  w.actualKernelW, w.actualKernelH, inputImageW, w.outputW,
                  w.outputH, strideW, strideH);
  Linear2_VWrite(&config->output, output, w.outputX, w.outputY, cOutStart,
                 w.outputW, w.outputH, outputImageW, stride);

  config->accum.strideMinusOne = stride - 1;
  StartAccelerator();
}

// Currently hardcoded for 2D kernels.
void *Versat_MaxPool(void *inputX, void *output, int index, MaxPoolInfo *info) {
  forceDoubleLoop = true;
  volatile Top_MaxpoolConfig *config = &accelConfig->Top_Maxpool;
  ActivateMergedAccelerator(MergeType_Top_Maxpool);

  int channels = info->inputDims[1];

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

  // Flush the remaining data from the accelerator
  config->features.enabled = 0;
  config->output.enabled = 0;
  RunAccelerator(2);

  return output;
}

static inline void AveragePool_ProcessWindow(AdvancedWindow w, int channel,
                                             void *input, void *output,
                                             AveragePoolInfo *info) {
  volatile Top_AveragePoolConfig *config = &accelConfig->Top_AveragePool;

  int inputImageW = info->inputDims[3];
  int inputImageH = info->inputDims[2];

  int outputImageW = info->outputDims[3];
  int outputImageH = info->outputDims[2];

  int cInStart = channel * inputImageH * inputImageW;
  int cOutStart = channel * outputImageH * outputImageW;

  int stride = w.actualKernelW * w.actualKernelH;

  int strideW = info->strideDims[1];
  int strideH = info->strideDims[0];

  MaxPool2D_VRead(&config->features, input, w.inputX, w.inputY, cInStart,
                  w.actualKernelW, w.actualKernelH, inputImageW, w.outputW,
                  w.outputH, strideW, strideH);
  Linear2_VWrite(&config->output, output, w.outputX, w.outputY, cOutStart,
                 w.outputW, w.outputH, outputImageW, stride);

  config->averagePool_accum.strideMinusOne = stride - 1;
  config->invertedDivisor.constant = NoConvert(1.0f / (float)stride);
  StartAccelerator();
}

// Currently hardcoded for 2D kernels.
void *Versat_AveragePool(void *inputX, void *output, int index,
                         AveragePoolInfo *info) {
  forceDoubleLoop = true;
  volatile Top_AveragePoolConfig *config = &accelConfig->Top_AveragePool;
  ActivateMergedAccelerator(MergeType_Top_AveragePool);

  int channels = info->inputDims[1];

  ExtraInfo extra = CalculateExtraInfo_AveragePool(info);

  // Using NHWC
  for (int c = 0; c < channels; c++) {
    WindowGen genInst = StartWindowGen(&extra, false, false);
    WindowGen *gen = &genInst;

    for (; WindowGen_Valid(gen); WindowGen_Advance(gen)) {
      AdvancedWindow w = WindowGen_Get(gen);
      AveragePool_ProcessWindow(w, c, inputX, output, info);
    }
  }

  // Flush the remaining data from the accelerator
  config->features.enabled = 0;
  config->output.enabled = 0;
  RunAccelerator(2);

  return output;
}

void ConvWithBias_ProcessWindow(AdvancedWindow w, void *inputX, void *inputW,
                                void *output, float *bias, ConvInfo *info,
                                int inputC, int outputC) {
  volatile Top_ConvConfig *config = &accelConfig->Top_Conv;

  int inputImageW = info->inputDims[3];
  int inputImageC = inputC;

  int outputImageW = info->outputDims[3];
  int outputImageC = outputC;

  int kernelW = info->kernelDims[1];
  int kernelH = info->kernelDims[0];

  int stride = w.actualKernelW * w.actualKernelH * inputImageC;

  int convChannelSize = inputImageC;
  int kernelChannelSize = inputImageC;
  int group = info->group;

  int convStartC = 0; // We must always process the entire input channels.
  int outputStartC = w.startC;

  int featuresComputedPerRun = 1;

  Conv2D_NHWC_VRead(&config->features, inputX, w.inputX, w.inputY,
                    w.actualKernelW, w.actualKernelH, inputImageW, inputImageC,
                    convChannelSize, featuresComputedPerRun, convStartC);

  Weight2D_VRead(&config->weights, inputW, w.kernelStartW, w.kernelStartH,
                 w.actualKernelW, w.actualKernelH, kernelW, kernelH,
                 inputImageC, kernelChannelSize, featuresComputedPerRun,
                 convStartC, outputStartC);

  // Only outputs one now.
  Linear2_NHWC_VWrite(&config->output, output, w.outputX, w.outputY, w.outputH,
                      w.outputW, w.startC, outputC, featuresComputedPerRun,
                      outputImageW, stride);

  if (bias == NULL) {
    static float bias = 0.0f;
    LinearStrided_VRead(&config->bias, &bias, 1, 1);
  } else {
    LinearStrided_VRead(&config->bias, bias + outputStartC,
                        featuresComputedPerRun, stride);
  }

  config->myAccum.strideMinusOne = stride - 1;

  StartAccelerator();
}

void *Versat_Conv(void *inputX, void *inputW, void *output, int index,
                  ConvInfo *info) {
  Versat_ConvWithBias(inputX, inputW, NULL, output, index, info);
}

void *Versat_ConvWithBias(void *inputX, void *inputW, void *inputB,
                          void *output, int index, ConvInfo *info) {
  forceDoubleLoop = true;

  volatile Top_ConvConfig *config = &accelConfig->Top_Conv;

  Arena arenaInst = {};
  Arena *arena = &arenaInst;

  arena->allocated = 1024 * 1024 * 16;
  arena->mem = malloc(arena->allocated); // 16 Megabytes

  ActivateMergedAccelerator(MergeType_Top_Conv);

  int batches = info->inputDims[0];
  int inputChannels = info->inputDims[1];
  int inputImageW = info->inputDims[3];
  int inputImageH = info->inputDims[2];

  int outputChannels = info->outputDims[1];
  int outputImageH = info->outputDims[2];
  int outputImageW = info->outputDims[3];

  int inputSize = inputImageW * inputImageH * inputChannels;
  int outputSize = outputImageW * outputImageH * outputChannels;
  int group = info->group;

  Tensor inputTensor = CreateTensor_NoAllocate(info->inputDims, 4);
  inputTensor.data = inputX;

  for (int batch = 0; batch < batches; batch++) {
    ArenaMark mark = MarkArena(arena);

    // TODO: This technically depends on batch because we have group related
    // operations
    //       that change these values. If we remove them we can then push this
    //       outside the loop
    ExtraInfo extra = CalculateExtraInfo_Conv(info);
    // ExtraInfo_Print(extra);

    int64_t NHWCDims[] = {info->inputDims[0], info->inputDims[2],
                          info->inputDims[3], info->inputDims[1]};

    Tensor tempInputTensor = PushTensor(arena, NHWCDims, 4);

    Tensor_CheckCanary(tempInputTensor);

    Tensor tempOutputTensor = PushTensor(arena, info->outputDims, 4);

    Tensor_CheckCanary(tempInputTensor);

    int64_t kernelDims[] = {outputChannels, inputChannels / group,
                            info->kernelDims[1], info->kernelDims[0]};
    // Tensor kernel = CreateTensor_NoAllocate(kernelDims, 4);
    // kernel.data = inputW;

    Tensor_CheckCanary(tempInputTensor);

    int kernelSize = Dimensions_Size(CreateDimensions(kernelDims, 4));

    float *tempInput = tempInputTensor.data;
    float *tempOutput = tempOutputTensor.data;

    float *inputView = (float *)inputX;
    float *biasView = (float *)inputB;

    inputView += batch * inputSize;

    Tensor_CheckCanary(tempInputTensor);

    // Convert NCHW to NHWC
    for (int y = 0; y < inputImageH; y++) {
      for (int x = 0; x < inputImageW; x++) {
        for (int c = 0; c < inputChannels; c++) {
          int NCHW_Index =
              c * (inputImageH * inputImageW) + y * inputImageW + x;
          int NHWC_Index =
              y * (inputImageW * inputChannels) + x * inputChannels + c;

          tempInput[NHWC_Index] = inputView[NCHW_Index];
        }
      }
    }

    Tensor_CheckCanary(tempInputTensor);

    // Extract the channel
    if (group != 1) {
      extra.inputImageC /= group;
      extra.outputImageC /= group;

      Dimensions dims = CreateDimensions(info->inputDims, 4);
      dims.data[1] /= group;

      int size = Dimensions_Size(dims);

      Dimensions outDims = CreateDimensions(info->outputDims, 4);
      outDims.data[1] /= group;

      int64_t NHWCOutDims[4] = {outDims.data[0], outDims.data[2],
                                outDims.data[3], outDims.data[1]};
      Tensor tempGroupTensor = PushTensor(arena, NHWCOutDims, 4);
      float *tempGroupOutput = tempGroupTensor.data;

      int index = 0;
      for (int g = 0; g < group; g++) {
        int s = extra.inputImageC;
        int o = extra.outputImageC;
        Tensor extracted =
            Tensor_ExtractView(tempInputTensor, 3, g * s, s, arena);

        WindowGen genInst = StartWindowGen(&extra, true, false);
        WindowGen *gen = &genInst;

        float *trueBias = biasView;
        if (trueBias != NULL) {
          trueBias += (g * extra.outputImageC);
        }

        for (; WindowGen_Valid(gen); WindowGen_Advance(gen)) {
          AdvancedWindow w = WindowGen_Get(gen);
          ConvWithBias_ProcessWindow(
              w, extracted.data, ((float *)inputW) + g * (kernelSize / group),
              tempGroupOutput, trueBias, info, s, o);
        }

        // Flush the remaining data from the accelerator
        // TODO: Not efficient but not worrying about it for now.
        config->features.enabled = 0;
        config->weights.enabled = 0;
        config->output.enabled = 0;
        config->bias.enabled = 0;
        RunAccelerator(2);

        silent_clear_cache();

        // We obtain the result in NHWC format and we need to "concatenate" this
        // with the output that we are building.
        // The output is also in NHWC format.
        // The problem is that the concatenation assumes that we are in NCHW
        // format.

        //
        int transposeDims[] = {0, 3, 1, 2};
        Tensor transposed =
            Tensor_Transpose(tempGroupTensor, transposeDims, arena);

        float *outputView = (float *)output;
        outputView += batch * outputSize; // + g * (outputSize / group);
        for (int i = 0; i < outputSize / group; i++) {
          outputView[index++] = transposed.data[i];
        }

        Tensor_CheckCanary(extracted);
        Tensor_CheckCanary(transposed);
      }

      Tensor_CheckCanary(tempGroupTensor);
    } else {

      WindowGen genInst = StartWindowGen(&extra, true, false);
      WindowGen *gen = &genInst;

      for (; WindowGen_Valid(gen); WindowGen_Advance(gen)) {
        AdvancedWindow w = WindowGen_Get(gen);
        ConvWithBias_ProcessWindow(w, tempInput, inputW, tempOutput, biasView,
                                   info, info->inputDims[1],
                                   info->outputDims[1]);
      }

      // Flush the remaining data from the accelerator
      config->features.enabled = 0;
      config->weights.enabled = 0;
      config->output.enabled = 0;
      config->bias.enabled = 0;
      RunAccelerator(2);

      float *outputView = (float *)output;
      outputView += batch * outputSize;

      silent_clear_cache();

      // Convert NHWC to NCHW
      for (int c = 0; c < outputChannels; c++) {
        for (int y = 0; y < outputImageH; y++) {
          for (int x = 0; x < outputImageW; x++) {
            int NCHW_Index =
                c * (outputImageH * outputImageW) + y * outputImageW + x;
            int NHWC_Index =
                y * (outputImageW * outputChannels) + x * outputChannels + c;

            outputView[NCHW_Index] = tempOutput[NHWC_Index];
          }
        }
      }
    }

    Tensor_CheckCanary(tempInputTensor);
    Tensor_CheckCanary(tempOutputTensor);

    MarkPop(mark);
  }

  return output;
}

void *Versat_MatMul(void *inputA, void *inputB, void *output, int index,
                    MatMulInfo *info) {

  ActivateMergedAccelerator(MergeType_Top_MatMul);
  volatile Top_MatMulConfig *config = &accelConfig->Top_MatMul;

  int totalBSize = info->inputBDims[0] * info->inputBDims[1];

  float *tempB = (float *)malloc(sizeof(float) * totalBSize);

  float *viewA = (float *)inputA;
  float *viewB = (float *)inputB;
  float *viewOut = (float *)output;

  int AH = info->inputADims[0];
  int AW = info->inputADims[1];

  int BH = info->inputBDims[0];
  int BW = info->inputBDims[1];

  int OH = info->outputDims[0];
  int OW = info->outputDims[1];

  if (AW != BH) {
    versat_printf("Something very wrong is happening in MatMul\n");
  }

  // After transpose, matrix goes from size BH,BW to BW,BH
  for (int y = 0; y < BH; y++) {
    for (int x = 0; x < BW; x++) {
      // Transposing B
      tempB[x * BH + y] = viewB[y * BW + x];
    }
  }

  silent_clear_cache();

  for (int y = 0; y < OH; y++) {
    for (int x = 0; x < OW; x++) {
      float *lineAStart = &viewA[y * AW];
      float *lineBStart = &tempB[x * AW];

      float *out = &viewOut[y * OW + x];

      Linear_VRead(&config->leftRow, lineAStart, AW);
      Linear_VRead(&config->rightRow, lineBStart, BH);
      LinearStrided_VWrite(&config->output, out, 1, AW);

      config->myAccum.strideMinusOne = AW - 1;

      StartAccelerator();
    }
  }

  config->leftRow.enabled = 0;
  config->rightRow.enabled = 0;
  config->output.enabled = 0;
  RunAccelerator(2);

  free(tempB);

  return output;
}

void *Versat_Softmax(void *inputA, void *output, int index, SoftmaxInfo *info) {
  return Software_Softmax(inputA, output, index, info);
}
