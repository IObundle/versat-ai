#include "versat_private.h"

#include "versat_ai.h"

// nocheckin: Remove this after solving bug
#include <stdlib.h>
#include <string.h>

#define MAX(A, B) ((A) > (B) ? (A) : (B))
#define MIN(A, B) ((A) < (B) ? (A) : (B))

//#define LOW_OUTPUT

// ======================================
// Global stuff (versat side)

Arena arenaInst;
Arena *arena = &arenaInst;

uint64_t Versat_DefaultMeasureTime() { return 0; }
void Versat_DefaultTimeReset(){};
void Versat_DefaultClearCache(void *ptr, size_t size) {}

MeasureTimeFunction versat_time = Versat_DefaultMeasureTime;
TimeResetFunction versat_timeReset = Versat_DefaultTimeReset;
ClearCache versat_clearCache = Versat_DefaultClearCache;

TimeResetFunction Versat_SetTimeReset(TimeResetFunction func) {
  TimeResetFunction old = versat_timeReset;
  versat_timeReset = func;
  return old;
}

MeasureTimeFunction
Versat_SetTimeMeasurementFunction(MeasureTimeFunction func) {
  MeasureTimeFunction old = versat_time;
  versat_time = func;
  return old;
}

ClearCache Versat_SetClearCache(ClearCache func) {
  ClearCache old = versat_clearCache;
  versat_clearCache = func;
  return old;
}

void Assert_(bool cond, const char *msg, int line, const char *file) {
  if (!cond) {
    versat_printf("Assertion failed!\n");
    versat_printf("In file %s:%d\n", file, line);
    versat_printf("%s", msg);
  }
}

#define Assert(COND, MSG) Assert_(COND, MSG, __LINE__, __FILE__)

// ======================================
// Dimensions

Dimensions CreateDimensions(int64_t *dims, int numberDims) {
  Dimensions res = {};
  res.size = numberDims;
  for (int i = 0; i < numberDims; i++) {
    res.data[i] = dims[i];
  }
  return res;
}

void Dimensions_PrependInPlace(Dimensions *dim, int value) {
  Assert(dim->size + 1 <= MAX_DIMS, "MAX_DIMS overflow");
  for (int i = 0; i < dim->size; i++) {
    dim->data[i + 1] = dim->data[i];
  }
  dim->data[0] = value;
  dim->size += 1;
}

void Dimensions_AppendInPlace(Dimensions *dim, int value) {
  Assert(dim->size + 1 <= MAX_DIMS, "MAX_DIMS overflow");
  dim->data[dim->size] = value;
  dim->size += 1;
}

Dimensions Dimensions_Cut_GetLeft(Dimensions dim, int amount) {
  Dimensions res = {};

  if (amount == 0) {
    res.data[0] = 1;
    res.size = 1;
    return res;
  }

  int size = MIN(dim.size, amount);

  for (int i = 0; i < size; i++) {
    res.data[i] = dim.data[i];
  }
  res.size = size;

  return res;
}

Dimensions Dimensions_Cut_GetRight(Dimensions dim, int amount) {
  Dimensions res = {};

  if (amount == dim.size) {
    res.data[0] = 1;
    res.size = 1;
    return res;
  }

  int size = MAX(dim.size - amount, 0);
  for (int i = 0; i < size; i++) {
    res.data[i] = dim.data[amount + i];
  }
  res.size = size;

  return res;
}

int Dimensions_TotalSize(Dimensions dim) {
  int size = 1;
  for (int i = 0; i < dim.size; i++) {
    size *= dim.data[i];
  }
  return size;
}

// ======================================
// Address

// Proper dims are the dims used to calculate an index.
// Iteration dims are the iterations.
AddressGen StartAddress(int64_t *iterationDims, int64_t *properDims,
                        int numberDims) {
  AddressGen gen = {};

  for (int i = 0; i < numberDims; i++) {
    gen.iterationDims[i] = iterationDims[i];
    gen.properDims[i] = properDims[i];
  }
  gen.numberDims = numberDims;

  return gen;
}

AddressGen StartAddressFromDims(Dimensions dims, int iterDims) {
  AddressGen gen = {};

  for (int i = 0; i < dims.size; i++) {
    gen.properDims[i] = dims.data[i];
    gen.iterationDims[i] = dims.data[i];

    if (i >= iterDims) {
      gen.iterationDims[i] = 1;
    }
  }
  gen.numberDims = dims.size;

  return gen;
}

int Address_GetDim(AddressGen *gen, int index) {
  Assert(index < gen->numberDims, "Index greater than dimensions of Address");
  return gen->addressVars[index];
}

void Address_Print(AddressGen *gen) {
  for (int i = 0; i < gen->numberDims; i++) {
    if (i != 0) {
      versat_printf(" x ");
    }
    versat_printf("%d", gen->addressVars[i]);
  }

  versat_printf(" [");
  for (int i = 0; i < gen->numberDims; i++) {
    if (i != 0) {
      versat_printf(" x ");
    }
    versat_printf("%ld", gen->iterationDims[i]);
  }
  versat_printf("]\n");
}

int Address_GetValue(AddressGen *gen) {
  int address = 0;
  for (int i = 0; i < gen->numberDims; i++) {
    int index = gen->addressVars[i] + gen->offsetAddressVars[i];

    if (index >= gen->properDims[i]) {
      index = 0;
    }

    if (i > 0) {
      address *= gen->properDims[i];
    }
    address += index;
  }

  return address;
}

bool Address_IsValid(AddressGen *gen) {
  // Because we allow out of order advances, we need to check every
  for (int i = 0; i < gen->numberDims; i++) {
    if (gen->addressVars[i] >= gen->iterationDims[i]) {
      return false;
    }
  }

  for (int i = 0; i < gen->numberDims; i++) {
    if (gen->addressVars[i] >= gen->iterationDims[i]) {
      continue;
    } else {
      return true;
    }
  }
  return false;
}

void Address_Advance(AddressGen *gen) {
  if (gen->addressVars[0] >= gen->iterationDims[0]) {
    return;
  }

  for (int i = gen->numberDims - 1; i >= 0; i--) {
    if (i != 0 && gen->addressVars[i] + 1 >= gen->iterationDims[i]) {
      gen->addressVars[i] = 0;
      continue;
    } else {
      gen->addressVars[i] += 1;
      return;
    }
  }
}

void Address_AdvanceAxis(AddressGen *gen, int axisToAdvance) {
  // Any negative axis just puts the address gen into an invalid state
  if (axisToAdvance < 0) {
    gen->addressVars[0] = gen->iterationDims[0] + 1;
    return;
  }

  if (gen->addressVars[0] >= gen->iterationDims[0]) {
    return;
  }

  for (int i = axisToAdvance; i >= 0; i--) {
    if (i != 0 && gen->addressVars[i] + 1 >= gen->iterationDims[i]) {
      gen->addressVars[i] = 0;
      continue;
    } else {
      gen->addressVars[i] += 1;
      return;
    }
  }
}

AddressGen Address_Map(AddressGen *in, int64_t *biggerDim, int *stride) {
  AddressGen gen = *in;

  for (int i = 0; i < in->numberDims; i++) {
    gen.addressVars[i] *= stride[i];
    gen.iterationDims[i] = biggerDim[i];
    gen.properDims[i] = biggerDim[i];
  }

  return gen;
}

AddressGen Address_Map2(AddressGen *in, int64_t *biggerDim, int *stride,
                        int *offset) {
  AddressGen gen = *in;

  for (int i = 0; i < in->numberDims; i++) {
    gen.addressVars[i] *= stride[i];
    gen.addressVars[i] -= offset[i];
    gen.iterationDims[i] = biggerDim[i];
    gen.properDims[i] = biggerDim[i];
  }

  return gen;
}

void Address_Restart(AddressGen *gen) {
  for (int i = 0; i < gen->numberDims; i++) {
    gen->addressVars[i] = 0;
  }
}

// ======================================
// KernelGen

// KernelDims are the bounds of the dimensions that the KernelGen iterates over
// Example, if we have a layer of dim A,B,C,D and kernelSize of 2, then
// the kernel only iterates over the C and D dimensions, never A or B.
// kernelDims has kernelSize size and defines the boundary of the iteration
KernelGen StartKernel(AddressGen *address, int *kernelDims, int kernelSize) {
  KernelGen gen = {};
  // gen.address = address;

  int nonKernelDims = address->numberDims - kernelSize;

  for (int i = 0; i < nonKernelDims; i++) {
    gen.kernelDims[i] = 1;
  }
  gen.numberDims = address->numberDims;

  for (int i = 0; i < MAX_DIMS; i++) {
    gen.kernelDilations[i] = 1;
  }

  for (int i = 0; i < kernelSize; i++) {
    gen.kernelDims[nonKernelDims + i] = kernelDims[i];
  }

  for (int i = 0; i < address->numberDims; i++) {
    gen.addressGenVars[i] = address->addressVars[i];
  }
  for (int i = 0; i < address->numberDims; i++) {
    gen.addressIterDims[i] = address->iterationDims[i];
  }
  for (int i = 0; i < address->numberDims; i++) {
    gen.addressProperDims[i] = address->properDims[i];
  }

  return gen;
}

KernelGen StartKernel_IterateOneDimOnly(AddressGen *address, int dimToIterate,
                                        int start, int end) {
  int dims[] = {1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1};

  KernelGen gen = StartKernel(address, dims, address->numberDims);

  gen.addressGenVars[dimToIterate] = 0;
  gen.kernelDims[dimToIterate] = end;
  gen.kernelVars[dimToIterate] = start;

  return gen;
}

void Kernel_PrintShort(KernelGen *gen) {
  versat_printf(
      "Kernel is gonna iterate the base tensor in the following coordinates:");

  versat_printf(" [");
  for (int i = 0; i < gen->numberDims; i++) {
    if (i != 0) {
      versat_printf(" x ");
    }
    versat_printf("%ld - %ld", gen->addressGenVars[i],
                  gen->addressGenVars[i] + gen->kernelDims[i]);
  }
  versat_printf("]\n");
}

void Kernel_Print(KernelGen *gen) {
  for (int i = 0; i < gen->numberDims; i++) {
    if (i != 0) {
      versat_printf(" x ");
    }
    versat_printf("%d", gen->kernelVars[i]);
  }

  versat_printf(" [");
  for (int i = 0; i < gen->numberDims; i++) {
    if (i != 0) {
      versat_printf(" x ");
    }
    versat_printf("%ld", gen->kernelDims[i]);
  }
  versat_printf("]");

  versat_printf(" [");
  for (int i = 0; i < gen->numberDims; i++) {
    if (i != 0) {
      versat_printf(" x ");
    }
    versat_printf("%ld - %ld", gen->addressGenVars[i],
                  gen->addressGenVars[i] + gen->kernelDims[i]);
  }
  versat_printf("]\n");
}

int Kernel_GetValue(KernelGen *gen) {
  int properVars[MAX_DIMS];

  for (int i = 0; i < gen->numberDims; i++) {
    properVars[i] =
        gen->kernelVars[i] * gen->kernelDilations[i] + gen->addressGenVars[i];
  }

  int address = 0;
  for (int i = 0; i < gen->numberDims; i++) {
    int index = properVars[i];

    if (index >= gen->addressIterDims[i]) {
      index = 0;
    }

    if (i > 0) {
      address *= gen->addressIterDims[i];
    }
    address += index;
  }

  return address;
}

bool Kernel_IsValid(KernelGen *gen) {
  // Is this the only thing that we need?
  if (gen->kernelVars[0] >= gen->kernelDims[0]) {
    return false;
  }

  for (int i = 0; i < gen->numberDims; i++) {
    if (gen->kernelVars[i] >= gen->kernelDims[i]) {
      continue;
    } else {
      return true;
    }
  }
  return false;
}

bool Kernel_IsInsidePad(KernelGen *gen) {
  int properVars[MAX_DIMS];

  for (int i = 0; i < gen->numberDims; i++) {
    properVars[i] =
        gen->kernelVars[i] * gen->kernelDilations[i] + gen->addressGenVars[i];
  }

  for (int i = 0; i < gen->numberDims; i++) {
    if (properVars[i] < 0 || properVars[i] >= gen->addressProperDims[i]) {
      // versat_printf("Bad: %d %d
      // %d\n",i,properVars[i],gen->addressProperDims[i]);
      return true;
    }
  }

  return false;
}

void Kernel_Advance(KernelGen *gen) {
  if (gen->kernelVars[0] >= gen->kernelDims[0]) {
    return;
  }

  for (int i = gen->numberDims - 1; i >= 0; i--) {
    if (i != 0 && gen->kernelVars[i] + 1 >= gen->kernelDims[i]) {
      gen->kernelVars[i] = 0;
      continue;
    } else {
      gen->kernelVars[i] += 1;
      return;
    }
  }
}

// ======================================
// Misc

int64_t CalculateSizeOfDim(int64_t *dim, int dims) {
  int64_t size = 1;
  for (int i = 0; i < dims; i++) {
    size *= dim[i];
  }

  return size;
}

static inline float absf(float a) {
  if (a < 0.0f) {
    return -a;
  }
  return a;
}

void AssertAlmostEqual(void *toTest, void *correctValues, int index,
                       float precision, LayerInfo *info) {
  float *test = (float *)toTest;
  float *correct = (float *)correctValues;

  size_t outputSize = info->outputSize / sizeof(float);

#ifndef LOW_OUTPUT
  // versat_printf("Gonna check output of layer: %d\n", index);
#endif

  if (outputSize == 0) {
    versat_printf(
        "Error, AssertAlmostEqual with output size of 0. Should not be "
        "possible. Check onnx generated info.\n");
    return;
  }

  int maxIncorrect = 10;
  bool printOk = true;

  // Make sure that cache is not affecting the verification process
  // TODO: Proper boundaries
  versat_clearCache(NULL, 0);

  int incorrectFound = 0;
  for (int i = 0; i < outputSize; i++) {
    // versat_printf("%f %f\n", correct[i],test[i]);
    if (absf(correct[i] - test[i]) > precision) {
      if (incorrectFound == 0) {
        versat_printf("\n");
        versat_printf("[%s] (Layer %d) FAIL:\n", info->typeName, index);
      }
      versat_printf("  Index: %4d Different values %.4f %.4f\n", i, correct[i],
                    test[i]);
      if (i > 0) {
        versat_printf("    PreviousValue: %.4f\n", test[i - 1]);
      }
      incorrectFound += 1;
    }

    if (incorrectFound >= maxIncorrect) {
      versat_printf("More than %d incorrect found, quitting early\n",
                    maxIncorrect);
      versat_printf("\n");
      break;
    }
  }

#ifndef LOW_OUTPUT
  if (printOk && incorrectFound == 0) {
    versat_printf("[%30s] (Layer %4d) - OK\n", info->typeName, index);
  }
#endif
}

// Based on quake fast inverse square root function.
float my_invsqrt(float number) {
  long i;
  float x2, y;
  const float threehalfs = 1.5F;

  x2 = number * 0.5F;
  y = number;
  i = *(long *)&y;
  i = 0x5f3759df - (i >> 1);
  y = *(float *)&i;
  y = y * (threehalfs - (x2 * y * y));
  y = y * (threehalfs - (x2 * y * y));

  return y;
}

// ======================================
// Extra Info

void ExtraInfo_Print(ExtraInfo e) {
  versat_printf("ExtraInfo:\n");
  versat_printf("strideW: %d\n", e.strideW);
  versat_printf("strideH: %d\n", e.strideH);
  versat_printf("kernelW: %d\n", e.kernelW);
  versat_printf("kernelH: %d\n", e.kernelH);
  versat_printf("inputImageW: %d\n", e.inputImageW);
  versat_printf("inputImageH: %d\n", e.inputImageH);
  versat_printf("inputImageC: %d\n", e.inputImageC);
  versat_printf("outputImageW: %d\n", e.outputImageW);
  versat_printf("outputImageH: %d\n", e.outputImageH);
  versat_printf("outputImageC: %d\n", e.outputImageC);
  versat_printf("leftPadW: %d\n", e.leftPadW);
  versat_printf("leftPadH: %d\n", e.leftPadH);
  versat_printf("rightPadW: %d\n", e.rightPadW);
  versat_printf("rightPadH: %d\n", e.rightPadH);
  versat_printf("padW: %d\n", e.padW);
  versat_printf("padH: %d\n", e.padH);
  versat_printf("\n");
}

ExtraInfo CalculateExtraInfo_MaxPool(MaxPoolInfo *info) {
  ExtraInfo res = {};

  int64_t *inputDims = VERSAT_MaxPoolInfo_inputDims(info);
  int64_t *outputDims = VERSAT_MaxPoolInfo_outputDims(info);
  int *kernelDims = VERSAT_MaxPoolInfo_kernelDims(info);
  int *strideDims = VERSAT_MaxPoolInfo_strideDims(info);
  int *padsDims = VERSAT_MaxPoolInfo_padsDims(info);

  res.strideW = strideDims[1];
  res.strideH = strideDims[0];

  res.kernelW = kernelDims[1];
  res.kernelH = kernelDims[0];

  res.inputImageW = inputDims[3];
  res.inputImageH = inputDims[2];
  res.inputImageC = inputDims[1];

  res.outputImageC = outputDims[1];
  res.outputImageH = outputDims[2];
  res.outputImageW = outputDims[3];

  if (info->padding == PaddingType_NOTSET) {
    // TODO: Need a better way of handling errors in this layer, I think.
    if (info->padsSize != 4) {
      versat_printf("ERROR, pads size is not expected");
      return (ExtraInfo){};
    }

    res.leftPadW = padsDims[1];
    res.leftPadH = padsDims[0];

    res.rightPadW = padsDims[3];
    res.rightPadH = padsDims[2];

    res.padW = padsDims[1] + padsDims[3];
    res.padH = padsDims[0] + padsDims[2];
  } else if (info->padding == PaddingType_SAME_LOWER ||
             info->padding == PaddingType_SAME_UPPER) {
    res.padW = MAX(0, (res.outputImageW - 1) * res.strideW + res.kernelW -
                          res.inputImageW);
    res.padH = MAX(0, (res.outputImageH - 1) * res.strideH + res.kernelH -
                          res.inputImageH);

    int halfW = res.padW / 2;
    int halfH = res.padH / 2;

    res.leftPadW = halfW;
    res.rightPadW = halfW;
    res.leftPadH = halfH;
    res.rightPadH = halfH;

    if (res.padW % 2 == 1) {
      if (info->padding == PaddingType_SAME_LOWER) {
        res.leftPadW += 1;
      } else {
        res.rightPadW += 1;
      }
    }

    if (res.padH % 2 == 1) {
      if (info->padding == PaddingType_SAME_LOWER) {
        res.leftPadH += 1;
      } else {
        res.rightPadH += 1;
      }
    }
  }

  return res;
}

ExtraInfo CalculateExtraInfo_AveragePool(AveragePoolInfo *info) {
  ExtraInfo res = {};

  int64_t *inputDims = VERSAT_AveragePoolInfo_inputDims(info);
  int64_t *outputDims = VERSAT_AveragePoolInfo_outputDims(info);
  int *kernelDims = VERSAT_AveragePoolInfo_kernelDims(info);
  int *strideDims = VERSAT_AveragePoolInfo_strideDims(info);
  int *padsDims = VERSAT_AveragePoolInfo_padsDims(info);

  res.strideW = strideDims[1];
  res.strideH = strideDims[0];

  res.kernelW = kernelDims[1];
  res.kernelH = kernelDims[0];

  res.inputImageW = inputDims[3];
  res.inputImageH = inputDims[2];
  res.inputImageC = inputDims[1];

  res.outputImageC = outputDims[1];
  res.outputImageH = outputDims[2];
  res.outputImageW = outputDims[3];

  if (info->padding == PaddingType_NOTSET) {
    // TODO: Need a better way of handling errors in this layer, I think.

    if (info->padsSize != 4) {
      versat_printf("ERROR, pads size is not expected");
      return (ExtraInfo){};
    }

    res.leftPadW = padsDims[1];
    res.leftPadH = padsDims[0];

    res.rightPadW = padsDims[3];
    res.rightPadH = padsDims[2];

    res.padW = padsDims[1] + padsDims[3];
    res.padH = padsDims[0] + padsDims[2];
  } else if (info->padding == PaddingType_SAME_LOWER ||
             info->padding == PaddingType_SAME_UPPER) {
    res.padW = MAX(0, (res.outputImageW - 1) * res.strideW + res.kernelW -
                          res.inputImageW);
    res.padH = MAX(0, (res.outputImageH - 1) * res.strideH + res.kernelH -
                          res.inputImageH);

    int halfW = res.padW / 2;
    int halfH = res.padH / 2;

    res.leftPadW = halfW;
    res.rightPadW = halfW;
    res.leftPadH = halfH;
    res.rightPadH = halfH;

    if (res.padW % 2 == 1) {
      if (info->padding == PaddingType_SAME_LOWER) {
        res.leftPadW += 1;
      } else {
        res.rightPadW += 1;
      }
    }

    if (res.padH % 2 == 1) {
      if (info->padding == PaddingType_SAME_LOWER) {
        res.leftPadH += 1;
      } else {
        res.rightPadH += 1;
      }
    }
  }

  return res;
}

ExtraInfo CalculateExtraInfo_Conv(ConvInfo *info) {
  ExtraInfo res = {};

  int64_t *inputDims = VERSAT_ConvInfo_inputDims(info);
  int64_t *outputDims = VERSAT_ConvInfo_outputDims(info);
  int *kernelDims = VERSAT_ConvInfo_kernelDims(info);
  int *strideDims = VERSAT_ConvInfo_strideDims(info);
  int *padsDims = VERSAT_ConvInfo_padsDims(info);

  res.strideW = strideDims[1];
  res.strideH = strideDims[0];

  res.kernelW = kernelDims[1];
  res.kernelH = kernelDims[0];

  res.inputImageW = inputDims[3];
  res.inputImageH = inputDims[2];
  res.inputImageC = inputDims[1];

  if (info->isNHWC) {
    res.inputImageC = inputDims[3];
    res.inputImageH = inputDims[1];
    res.inputImageW = inputDims[2];
  }

  res.outputImageC = outputDims[1];
  res.outputImageH = outputDims[2];
  res.outputImageW = outputDims[3];

  if (info->isNHWC) {
    res.outputImageC = outputDims[3];
    res.outputImageH = outputDims[1];
    res.outputImageW = outputDims[2];
  }

  if (info->padding == PaddingType_NOTSET) {
    // TODO: Need a better way of handling errors in this layer, I think.
    if (info->padsSize != 4) {
      versat_printf("ERROR, pads size is not expected");
      return (ExtraInfo){};
    }

    res.leftPadW = padsDims[1];
    res.leftPadH = padsDims[0];

    res.rightPadW = padsDims[3];
    res.rightPadH = padsDims[2];

    res.padW = padsDims[1] + padsDims[3];
    res.padH = padsDims[0] + padsDims[2];
  } else if (info->padding == PaddingType_SAME_LOWER ||
             info->padding == PaddingType_SAME_UPPER) {
    res.padW = MAX(0, (res.outputImageW - 1) * res.strideW + res.kernelW -
                          res.inputImageW);
    res.padH = MAX(0, (res.outputImageH - 1) * res.strideH + res.kernelH -
                          res.inputImageH);

    int halfW = res.padW / 2;
    int halfH = res.padH / 2;

    res.leftPadW = halfW;
    res.rightPadW = halfW;
    res.leftPadH = halfH;
    res.rightPadH = halfH;

    if (res.padW % 2 == 1) {
      if (info->padding == PaddingType_SAME_LOWER) {
        res.leftPadW += 1;
      } else {
        res.rightPadW += 1;
      }
    }

    if (res.padH % 2 == 1) {
      if (info->padding == PaddingType_SAME_LOWER) {
        res.leftPadH += 1;
      } else {
        res.rightPadH += 1;
      }
    }
  }

  return res;
}
// ======================================
// WindowGen

WindowGen StartWindowGen(ExtraInfo *info, bool iterateC, bool isNCHW) {
  WindowGen res = {};
  res.info = info;
  res.iterateC = iterateC;
  res.isNCHW = isNCHW;
  res.advanceC = 1;
  return res;
}

WindowGen StartAdvancedWindowGen(ExtraInfo *info, bool iterateC, bool isNCHW,
                                 int xMaxAdvance, int yMaxAdvance,
                                 int cMaxAdvance) {
  WindowGen res = {};
  res.info = info;
  res.iterateC = iterateC;
  res.isNCHW = isNCHW;
  res.advanceX = xMaxAdvance;
  res.advanceY = yMaxAdvance;
  res.advanceC = cMaxAdvance;
  return res;
}

void AdvancedWindow_Print(AdvancedWindow window) {
  bool printedOnce = false;
  if (window.padding & PaddingRegion_TOP) {
    versat_printf("Pad_TOP");
    printedOnce = true;
  }
  if (window.padding & PaddingRegion_BOTTOM) {
    if (printedOnce) {
      versat_printf(" | ");
    }
    versat_printf("Pad_BOTTOM");
    printedOnce = true;
  }
  if (window.padding & PaddingRegion_LEFT) {
    if (printedOnce) {
      versat_printf(" | ");
    }
    versat_printf("Pad_LEFT");
    printedOnce = true;
  }
  if (window.padding & PaddingRegion_RIGHT) {
    if (printedOnce) {
      versat_printf(" | ");
    }
    versat_printf("Pad_RIGHT");
    printedOnce = true;
  }

  versat_printf("\n");

  versat_printf("Output pos: X:%d,Y:%d (C:%d)\n", window.outputX,
                window.outputY, window.outputC);
  versat_printf("Input pos: (%d,%d)\n", window.inputX, window.inputY);

  if (window.entireWindowInsidePadding) {
    versat_printf("Window inside padding\n");
  } else {
    versat_printf("WindowSize (Out view): %d %d %d\n", window.outputSizeC,
                  window.outputH, window.outputW);
    versat_printf("KernelSizeAndOffset: %d:%d - %d:%d\n", window.actualKernelW,
                  window.kernelStartW, window.actualKernelH,
                  window.kernelStartH);
  }
}

AdvancedWindow WindowGen_Get(WindowGen *gen) {
  AdvancedWindow res = {};

  res.outputX = gen->currentOutputX;
  res.outputY = gen->currentOutputY;
  res.outputC = gen->currentOutputC;

  res.startC = gen->currentOutputC;
  res.inputX = gen->currentOutputX * gen->info->strideW;
  res.inputY = gen->currentOutputY * gen->info->strideH;

  // Currently we assume a window size of 1, although need to add the better
  // logic to suport more windows and improve performance.

  // The only thing that we need to care about is the windows that are near
  // padding regions the fact that the accelerator must contain enough memory to
  // support a window and that we must make sure that the height of the window
  // is stable. ( So that we iterate over all the pixels correctly).
  res.outputW = 1;
  res.outputH = 1;
  res.outputSizeC = gen->advanceC;

  if (res.outputSizeC + res.outputC >= gen->info->outputImageC) {
    res.outputSizeC = gen->info->outputImageC - res.outputC;
    if (res.outputSizeC <= 0) {
      versat_printf("ERROR, CANNOT HAVE OUTPUT SIZE LOWER OR EQUAL TO 0: %d",
                    res.outputSizeC);
    }
  }

  // By default, input equals kernel size
  res.actualKernelW = gen->info->kernelW;
  res.actualKernelH = gen->info->kernelH;

  res.inputX -= gen->info->leftPadW;
  res.inputY -= gen->info->leftPadH;

  // TODO: For the cases without padding, we can support bigger
  //       windows. We mainly want to center the logic around
  //       how much internal memory the accelerator supports (limiting factor
  //       for window size) and of course the boundaries between padding, since
  //       we cannot process different padding boundaries in the same run.

  // NOTE: Any amount of padding basically shifts the kernel and changes the
  // input window size.
  //       Difference between left and right padding is wether we change the
  //       start or not. The size of the kernel always changes.

  // This logic only works if we make sure that we can have a one by one window
  // size at the extreme points
  if (res.inputX < 0) {
    int offset = -res.inputX;
    res.actualKernelW -= offset;
    res.kernelStartW = offset;
    res.padding |= PaddingRegion_LEFT;
    res.inputX = 0;
  }
  if (res.inputX + res.actualKernelW > gen->info->inputImageW) {
    int offset = (res.inputX + res.actualKernelW) - gen->info->inputImageW;
    res.actualKernelW -= offset;
    res.padding |= PaddingRegion_RIGHT;
  }

  if (res.inputY < 0) {
    int offset = -res.inputY;
    res.actualKernelH -= offset;
    res.kernelStartH = offset;
    res.padding |= PaddingRegion_TOP;
    res.inputY = 0;
  }
  if (res.inputY + res.actualKernelH > gen->info->inputImageH) {
    int offset = (res.inputY + res.actualKernelH) - gen->info->inputImageH;
    res.actualKernelH -= offset;
    res.padding |= PaddingRegion_BOTTOM;
  }

  // In this case we are inside the entirity of the padding section, which means
  // that we do not actually want to do anything. It should just be zero, right?
  if (res.actualKernelH <= 0 || res.actualKernelW <= 0) {
    res.entireWindowInsidePadding = true;
  }

  return res;
}

void WindowGen_GetTruePadding(WindowGen *gen, AdvancedWindow *out) {
  out->outputX = gen->currentOutputX;
  out->outputY = gen->currentOutputY;
  out->outputC = gen->currentOutputC;

  out->startC = gen->currentOutputC;
  out->inputX = gen->currentOutputX * gen->info->strideW;
  out->inputY = gen->currentOutputY * gen->info->strideH;

  // Currently we assume a window size of 1, although need to add the better
  // logic to suport more windows and improve performance.

  // The only thing that we need to care about is the windows that are near
  // padding regions the fact that the accelerator must contain enough memory to
  // support a window and that we must make sure that the height of the window
  // is stable. ( So that we iterate over all the pixels correctly).
  out->outputW = gen->advanceX;
  out->outputH = gen->advanceY;
  out->outputSizeC = gen->advanceC;

  // NOTE: There is some bug related to group which this piece of code hides.
  if (out->outputSizeC + out->outputC >= gen->info->outputImageC) {
    out->outputSizeC = gen->info->outputImageC - out->outputC;
    if (out->outputSizeC <= 0) {
      versat_printf("ERROR, CANNOT HAVE OUTPUT SIZE LOWER OR EQUAL TO 0: %d",
                    out->outputSizeC);
    }
  }

  // Puts window back into boundaries if it gets outside
  if (out->outputW + out->outputX >= gen->info->outputImageW) {
    out->outputW = gen->info->outputImageW - out->outputX;
  }
  if (out->outputH + out->outputY >= gen->info->outputImageH) {
    out->outputH = gen->info->outputImageH - out->outputY;
  }

  // By default, input equals kernel size
  out->actualKernelW = gen->info->kernelW;
  out->actualKernelH = gen->info->kernelH;
}

void WindowGen_Advance(WindowGen *gen) {
  AdvancedWindow window = WindowGen_Get(gen);

  if (gen->iterateC) {
    if (gen->isNCHW) {
      gen->currentOutputX += window.outputW;
      if (gen->currentOutputX >= gen->info->outputImageW) {
        gen->currentOutputX = 0;
        gen->currentOutputY += window.outputH;
      }

      if (gen->currentOutputY >= gen->info->outputImageH) {
        gen->currentOutputY = 0;
        gen->currentOutputC += window.outputSizeC;
      }

      if (gen->currentOutputC >= gen->info->outputImageC) {
        gen->currentOutputC = -1;
        gen->currentOutputX = -1;
        gen->currentOutputY = -1;
      }
    } else {
      // NHWC
      gen->currentOutputC += window.outputSizeC;
      if (gen->currentOutputC >= gen->info->outputImageC) {
        gen->currentOutputC = 0;
        gen->currentOutputX += window.outputW;
      }

      if (gen->currentOutputX >= gen->info->outputImageW) {
        gen->currentOutputX = 0;
        gen->currentOutputY += window.outputH;
      }

      if (gen->currentOutputY >= gen->info->outputImageH) {
        gen->currentOutputC = -1;
        gen->currentOutputX = -1;
        gen->currentOutputY = -1;
      }
    }
  } else {
    gen->currentOutputX += window.outputW;
    if (gen->currentOutputX >= gen->info->outputImageW) {
      gen->currentOutputX = 0;
      gen->currentOutputY += window.outputH;
    }

    if (gen->currentOutputY >= gen->info->outputImageH) {
      gen->currentOutputX = -1;
      gen->currentOutputY = -1;
    }
  }
}

void WindowGen_AdvanceTruePadding(WindowGen *gen, AdvancedWindow window) {
  if (gen->iterateC) {
    if (gen->isNCHW) {
      gen->currentOutputX += window.outputW;
      if (gen->currentOutputX >= gen->info->outputImageW) {
        gen->currentOutputX = 0;
        gen->currentOutputY += window.outputH;
      }

      if (gen->currentOutputY >= gen->info->outputImageH) {
        gen->currentOutputY = 0;
        gen->currentOutputC += window.outputSizeC;
      }

      if (gen->currentOutputC >= gen->info->outputImageC) {
        gen->currentOutputC = -1;
        gen->currentOutputX = -1;
        gen->currentOutputY = -1;
      }
    } else {
      // NHWC
      gen->currentOutputC += window.outputSizeC;
      if (gen->currentOutputC >= gen->info->outputImageC) {
        gen->currentOutputC = 0;
        gen->currentOutputX += window.outputW;
      }

      if (gen->currentOutputX >= gen->info->outputImageW) {
        gen->currentOutputX = 0;
        gen->currentOutputY += window.outputH;
      }

      if (gen->currentOutputY >= gen->info->outputImageH) {
        gen->currentOutputC = -1;
        gen->currentOutputX = -1;
        gen->currentOutputY = -1;
      }
    }
  } else {
    gen->currentOutputX += window.outputW;
    if (gen->currentOutputX >= gen->info->outputImageW) {
      gen->currentOutputX = 0;
      gen->currentOutputY += window.outputH;
    }

    if (gen->currentOutputY >= gen->info->outputImageH) {
      gen->currentOutputX = -1;
      gen->currentOutputY = -1;
    }
  }
}

bool WindowGen_Valid(WindowGen *gen) {
  bool res = (gen->currentOutputX != -1 && gen->currentOutputY != -1);
  return res;
}

// ======================================
// Tensors

Tensor CreateTensor_NoAllocate(int64_t *dims, int numberDims) {
  Tensor tensor = {};
  tensor.dims.size = numberDims;

  int size = 1;
  for (int i = 0; i < numberDims; i++) {
    tensor.dims.data[i] = dims[i];
    size *= dims[i];
  }

  return tensor;
}

int Tensor_Size(Tensor tensor) {
  int size = 1;
  for (int i = 0; i < tensor.dims.size; i++) {
    size *= tensor.dims.data[i];
  }

  return size;
}

void Tensor_Print(Tensor tensor) {
  int size = Tensor_Size(tensor);

  for (int i = 0; i < tensor.dims.size; i++) {
    if (i != 0) {
      versat_printf("x ");
    }
    versat_printf("%d ", tensor.dims.data[i]);
  }
  versat_printf("\n");
  for (int i = 0; i < size; i++) {
    versat_printf("%f\n", tensor.data[i]);
  }
}

typedef struct {
  void *outputMem;
  void *tempMem;
  void **inputs;
  void *modelMem;
  void *correctData;
} InferenceState;

void *GetSourcePointer(InferenceState *state, DataSource source) {
  switch (source.type) {
  case SourceType_OUTPUT_MEM: {
    return VERSAT_OFFSET_PTR(state->outputMem, source.memOffset);
  } break;
  case SourceType_TEMP_MEM: {
    return VERSAT_OFFSET_PTR(state->tempMem, source.memOffset);
  } break;
  case SourceType_INPUT: {
    return state->inputs[source.inputIndex];
  } break;
  case SourceType_MODEL_MEM: {
    return VERSAT_OFFSET_PTR(state->modelMem, source.memOffset);
  } break;
  case SourceType_CORRECT_MEM: {
    return VERSAT_OFFSET_PTR(state->correctData, source.memOffset);
  } break;
  }
}

void DataSource_Print(DataSource source) {
  switch (source.type) {
  case SourceType_OUTPUT_MEM: {
    versat_printf("Output_Mem: %d", source.memOffset);
  } break;
  case SourceType_TEMP_MEM: {
    versat_printf("Temp_Mem: %d", source.memOffset);
  } break;
  case SourceType_INPUT: {
    versat_printf("Input index: %d", source.inputIndex);
  } break;
  case SourceType_MODEL_MEM: {
    versat_printf("Model_Mem: %d", source.memOffset);
  } break;
  case SourceType_CORRECT_MEM: {
    versat_printf("Correct_Mem: %d", source.memOffset);
  } break;
  default: {
    versat_printf("Unknown data source type: %d", source.type);
  } break;
  }
  versat_printf("\n");
}

void Operation_Print(Operation *op) {
  versat_printf("Operation size: %d\n", op->operatorSize);
  versat_printf("Operation type: %d\n", op->type);
  versat_printf("Uses software: %s\n", op->useSoftware ? "True" : "False");
  versat_printf("Output:\n");
  versat_printf("  ");
  DataSource_Print(op->output);
  versat_printf("\n");

  versat_printf("Correct Output:\n");
  versat_printf("  ");
  DataSource_Print(op->correctOutput);
  versat_printf("\n");

  versat_printf("Inputs: %d\n", op->nInputs);
  for (uint32_t i = 0; i < op->nInputs; i++) {
    versat_printf("  ");
    DataSource_Print(op->inputs[i]);
    versat_printf("\n");
  }
}

void *Operation_GetOperationInfo(Operation *op) {
  void *res = VERSAT_OFFSET_PTR(
      op, (sizeof(Operation) + sizeof(DataSource) * op->nInputs));
  return res;
}

static void PrintU64(uint64_t n) {
  char buffer[32];
  char buffer2[32];

  for (int i = 0; i < 32; i++) {
    buffer[i] = 0;
    buffer2[i] = 0;
  }

  uint64_t v = n;
  int i = 0;
  if (v == 0) {
    buffer[i] = '0';
    i += 1;
  }
  while (v) {
    buffer[i] = (v % 10) + '0';
    v = v / 10;
    i += 1;
  }

  int index = 0;
  for (int j = i - 1; j >= 0; j--) {
    buffer2[index++] = buffer[j];
  }

  versat_printf("%s", buffer2);
}

static void PrintU64InHex(uint64_t n) {
  union {
    uint64_t u64;
    uint32_t u32[2];
  } conv;

  conv.u64 = n;

  versat_printf("%08x%08x\n", conv.u32[1], conv.u32[0]);
}

#include "versat_accel.h"

static ProfileSample *storedProfiles = 0;
static int maxProfiledSamples = 0;
static int profileIndex = 0;

void entry(const float tensor_input_1[1][32][32][3],
           float tensor_Identity[1][10]);

void PrintCurrentTime() {
  uint64_t now = versat_time();
  PrintU64(now);
  versat_printf("\n");
}

void PrintTimeDiff(uint64_t start) {
  uint64_t end = versat_time();
  uint64_t diff = end - start;

  versat_printf("Start,End,Diff\n");
  PrintU64(start);
  versat_printf("\n");
  PrintU64(end);
  versat_printf("\n");
  PrintU64(diff);
  versat_printf("\n\n");
}

InferenceOutput RunCompiledInference(CompiledModel *model, void *outputMemory,
                                     void *temporaryMemory, void **inputs,
                                     void *modelMemory, void *correctInput) {
  Operation *ptr = CompiledModel_Operations(model);

  uint64_t start = 0;

#if 0
  versat_printf("Onnx2c\n");

  versat_timeReset();
  start = versat_time();

  float **asFloat = (float **)inputs;
  entry(asFloat[0], (float *)outputMemory);

  PrintTimeDiff(start);
#endif

  InferenceState stateInst = {.outputMem = outputMemory,
                              .tempMem = temporaryMemory,
                              .inputs = inputs,
                              .modelMem = modelMemory,
                              .correctData = correctInput};

  char *correctInputAsChar = (char *)correctInput;
  char *savedCorrectMem = (char *)malloc(model->correctSize);
  memcpy(savedCorrectMem, correctInputAsChar, model->correctSize);

  char *correctModelMemory = (char *)modelMemory;
  char *savedModelMemory = (char *)malloc(model->modelSize);
  memcpy(savedModelMemory, correctModelMemory, model->modelSize);

#define PRINT_HELP 0

  InferenceState *state = &stateInst;

  Top_Conv_NumberUnits_Struct res = Top_Conv_NumberUnits();
  versat_printf("Add       parameters: %d\n", Top_Add_NumberUnits().val);
  versat_printf("Conv grid parameters: %d %d\n", res.gridX, res.gridY);

  versat_printf("VersatSoft\n");
  versat_timeReset();
  start = versat_time();
  for (uint32_t i = 0; i < model->nOperations;
       i++, ptr = VERSAT_OFFSET_PTR(ptr, ptr->operatorSize)) {
    bool useSoftware = ptr->useSoftware;

    void *info = Operation_GetOperationInfo(ptr);
    void *out = NULL;
    void *correctOutput = GetSourcePointer(state, ptr->correctOutput);

#if PRINT_HELP
    versat_printf("CorrectData\n");
    DataSource_Print(ptr->correctOutput);
    versat_printf("%p\n", correctOutput);
#endif

    void *input0 = NULL;
    void *input1 = NULL;
    void *input2 = NULL;
    void *input3 = NULL;
    void *input4 = NULL;
    if (ptr->nInputs > 0) {
      input0 = GetSourcePointer(state, ptr->inputs[0]);
#if PRINT_HELP
      versat_printf("Input0\n");
      DataSource_Print(ptr->inputs[0]);
      versat_printf("%p\n", input0);
#endif
    }
    if (ptr->nInputs > 1) {
      input1 = GetSourcePointer(state, ptr->inputs[1]);
#if PRINT_HELP
      versat_printf("Input1\n");
      DataSource_Print(ptr->inputs[1]);
      versat_printf("%p\n", input1);
#endif
    }
    if (ptr->nInputs > 2) {
      input2 = GetSourcePointer(state, ptr->inputs[2]);
    }
    if (ptr->nInputs > 3) {
      input3 = GetSourcePointer(state, ptr->inputs[3]);
    }
    if (ptr->nInputs > 4) {
      input4 = GetSourcePointer(state, ptr->inputs[4]);
    }

    void *output = GetSourcePointer(state, ptr->output);
#if PRINT_HELP
    versat_printf("OutputPos\n");
    DataSource_Print(ptr->output);
    versat_printf("%p\n", output);
    versat_printf("%d\n", ptr->outputSize);
#endif

#if 1
    // For testing purposes we initialize with a very likely bad value
    // To make sure that the operator is not skipping any computation
    float *asFloat = (float *)output;
    for (int i = 0; i < (ptr->outputSize / sizeof(float)); i++) {
      asFloat[i] = 123.321f;
    }
#endif

    versat_clearCache(NULL, 0);

    VersatProfileReset();

    // TODO: Could be generated by python stuff
    switch (ptr->type) {
    case OperatorType_Add: {
      if (useSoftware) {
        out = Software_Add(input0, input1, output, i, info);
      } else {
        out = Versat_Add(input0, input1, output, i, info);
      }
    } break;
    case OperatorType_Relu: {
      if (useSoftware) {
        out = Software_Relu(input0, output, i, info);
      } else {
        // out = Software_Relu(input0, output, i, info);
        out = Versat_Relu(input0, output, i, info);
      }
    } break;
    case OperatorType_MaxPool: {
      if (useSoftware) {
        out = Software_MaxPool(input0, output, i, info);
      } else {
        out = Versat_MaxPool(input0, output, i, info);
      }
    } break;
    case OperatorType_AveragePool: {
      if (useSoftware) {
        out = Software_AveragePool(input0, output, i, info);
      } else {
        out = Versat_AveragePool(input0, output, i, info);
      }
    } break;
    case OperatorType_Conv: {
      if (useSoftware) {
        out = Software_ConvWithBias(input0, input1, input2, output, i, info);
      } else {
        out = Versat_ConvWithBias(input0, input1, input2, output, i, info);
      }
    } break;
    case OperatorType_Reshape: {
      if (useSoftware) {
        out = Software_Reshape(input0, input1, output, i, info);
      } else {
        out = Versat_Reshape(input0, input1, output, i, info);
      }
    } break;
    case OperatorType_MatMul: {
      if (useSoftware) {
        out = Software_MatMul(input0, input1, output, i, info);
      } else {
        out = Versat_MatMul(input0, input1, output, i, info);
      }
    } break;
    case OperatorType_Softmax: {
      if (useSoftware) {
        out = Software_Softmax(input0, output, i, info);
      } else {
        out = Versat_Softmax(input0, output, i, info);
      }
    } break;
    case OperatorType_Transpose: {
      out = Software_Transpose(input0, output, i, info);
    } break;
    case OperatorType_BatchNormalization: {
      if (useSoftware) {
        out = Software_BatchNormalization(input0, input1, input2, input3,
                                          input4, output, i, info);
      } else {
        out = Versat_BatchNormalization(input0, input1, input2, input3, input4,
                                        output, i, info);
      }
    } break;
    case OperatorType_Dropout: {
      if (useSoftware) {
        out = Software_Dropout(input0, output, i, info);
      } else {
        out = Versat_Dropout(input0, output, i, info);
      }
    } break;
    case OperatorType_LRN: {
      if (useSoftware) {
        out = Software_LRN(input0, output, i, info);
      } else {
        out = Versat_LRN(input0, output, i, info);
      }
    } break;
    case OperatorType_Gemm: {
      if (useSoftware) {
        // out = Software_Gemm(input0, input1, input2, output, i, info);
      } else {
        out = Versat_Gemm(input0, input1, input2, output, i, info);
      }
    } break;
    case OperatorType_Pad: {
      out = Software_Pad(input0, output, i, info);
    } break;
    case OperatorType_FixPad: {
      out = Software_FixPad(input0, output, i, info);
    } break;

    default: {
      versat_printf("Unknown operation type: %d\n", ptr->type);
    } break;
    }

#if 0
    for (int i = 0; i < model->correctSize; i++) {
      if (savedCorrectMem[i] != correctInputAsChar[i]) {
        versat_printf("Correct input change!!!!!\n");
      }
    }

    for (int i = 0; i < model->modelSize; i++) {
      if (savedModelMemory[i] != correctModelMemory[i]) {
        versat_printf("Model memory change!!!!!\n");
      }
    }
#endif

#if 0
    // Run profile
    // ================================================================
    versat_printf("L:%d\n", i);
    VersatProfile p = VersatProfileGet();

    versat_printf("Cycles since last reset:");
    PrintU64(p.cyclesSinceLastReset);
    versat_printf("\n");

    // Versat profiling registers
    // ================================================
    if (1) {
      versat_printf("Runs:");
      PrintU64(p.runCount);
      versat_printf("\n");

      versat_printf("Cycles running:");
      PrintU64(p.runningCycles);
      versat_printf("\n");

      versat_printf("Databus valid:");
      PrintU64(p.databusValid);
      versat_printf("\n");

      versat_printf("Databus valid and ready:");
      PrintU64(p.databusValidAndReady);
      versat_printf("\n");

      versat_printf("ConfigurationsSet:");
      PrintU64(p.configurationsSet);
      versat_printf("\n");

      versat_printf("ConfigurationsSet while running:");
      PrintU64(p.configurationsSetWhileRunning);
      versat_printf("\n");

      ProfileResult res = Profile_Get();

      versat_printf("Profile samples: %d\n", res.amount);

      for (int i = 0; i < res.amount; i++) {
        ProfileSample sample = res.samples[i];

        versat_printf("%30s: ", sample.name);
        PrintU64(sample.time);
        versat_printf("\n");
      }

      Profile_Reset();
    }
#endif

#if 1
    // Check result of layer
    // ======================================================
    if (ptr->outputSize > 0) {
      LayerInfo layer = {};
      layer.outputSize = ptr->outputSize;
      layer.typeName = VERSAT_OperatorName(ptr->type, useSoftware);
      AssertAlmostEqual(out, correctOutput, i, ptr->precision, &layer);
    } else {
      const char *typeName = VERSAT_OperatorName(ptr->type, useSoftware);
      versat_printf("[%s] (Layer %d) NOT CHECKED (No validity data)\n",
                    typeName, i);
    }
#endif
  }

  PrintTimeDiff(start);
}

// ===============
//  Math utils

#define MATH_E 2.71828182846
#define MATH_PI 3.14159265359

double ABS(double x) { return x < 0 ? -x : x; }

typedef uint32_t u32;
typedef int32_t i32;

typedef uint8_t u8;

typedef struct {
  u32 mantissa : 23;
  u32 exponent : 8;
  u32 sign : 1;
} PackedFP;

typedef struct {
  u32 mantissa;
  i32 exponent;
  u8 sign;
} UnpackedFP;

UnpackedFP Unpack(float f, bool addImplicitBit) {
  PackedFP fp = *((PackedFP *)&f);

  UnpackedFP res = {};
  res.mantissa = fp.mantissa;

  if (addImplicitBit) {
    res.mantissa |= (1 << 23);
  }

  res.exponent = -127 + fp.exponent;
  res.sign = fp.sign;

  return res;
}

float Pack(UnpackedFP fp) {
  PackedFP res = {};
  res.sign = fp.sign;
  res.exponent = fp.exponent + 127;
  res.mantissa = fp.mantissa & ((1 << 24) - 1);

  return *((float *)&res);
}

static inline int Clamp(int min, int val, int max) {
  if (val < min) {
    return min;
  }
  if (val > max) {
    return max;
  }
  return val;
}

u32 Downsize(float f, int totalSize, int exponentAmount) {
  UnpackedFP unpacked = Unpack(f, false);

  int mantissaAmount = totalSize - 1 - exponentAmount;
  int signPos = totalSize - 1;

  u32 sign = (unpacked.sign) ? 1 : 0;

  int bias = (((1 << exponentAmount) / 2) - 1);

  u32 trueMantissa = Clamp(0, unpacked.mantissa >> (23 - mantissaAmount),
                           (1 << mantissaAmount) - 1);
  u32 trueExponent = Clamp(0, unpacked.exponent + (bias - 1), 31) &
                     ((1 << exponentAmount) - 1);

  u32 res =
      (trueMantissa | (trueExponent << mantissaAmount) | (sign << signPos));

  if (res >= (1 << totalSize)) {
    versat_printf("ERROR\n");
  }

  return res;
}

float Upsize(u32 in, int totalSize, int exponentAmount) {
  int mantissaAmount = totalSize - 1 - exponentAmount;

  u32 mantissaMask = ((1 << mantissaAmount) - 1);
  u32 exponentMask = ((1 << exponentAmount) - 1);

  u32 exponent = ((in >> mantissaAmount) & exponentMask);
  u32 mantissa = (in & mantissaMask) << (23 - mantissaAmount);
  int sign = ((in) >> (totalSize - 1)) & 1;

  bool subnormal = (exponent == 0);

  int bias = (((1 << exponentAmount) / 2) - 1);

  UnpackedFP unpacked = {};
  unpacked.sign = sign;
  unpacked.exponent = exponent - (bias - 1);
  unpacked.mantissa = mantissa;

  return Pack(unpacked);
}

void PrintBinary(u32 val) {
  for (int i = 31; i >= 0; i--) {
    u32 v = (val) & (1 << i);
    if (v) {
      versat_printf("1");
    } else {
      versat_printf("0");
    }
  }

  versat_printf("\n");
}

#define MAX_ITERS 20
double thetah_table[MAX_ITERS] = {
    0.549306, 0.255413, 0.125657, 0.062582, 0.031260, 0.015626, 0.007813,
    0.003906, 0.001953, 0.000977, 0.000488, 0.000244, 0.000122, 0.000061,
    0.000031, 0.000015, 0.000008, 0.000004, 0.000002, 0.000001};

double Cordic_arctanh(double y, double x) {
  double angle = 0.0;
  double P2i = 0.5;
  int k = 4;

  for (int i = 1; i < MAX_ITERS; i++) {
    double arc_tangent = thetah_table[i - 1];

    int iters = 1;
    if (i == k) {
      iters = 2;
      k = (3 * k) + 1;
    }

    for (int k = 0; k < iters; k++) {
      double sigma = 1.0;
      if (y < 0) {
        sigma = -1.0;
      }

      angle = angle + sigma * arc_tangent;
      double calcX = x - sigma * y * P2i;
      double calcY = y - sigma * x * P2i;

      x = calcX;
      y = calcY;
    }

    P2i /= 2.0;
  }

  return angle;
}

double Cordic_log(double in) {
  double val = in;

  if (in < 0.0f) {
    u32 minusInf = 0x7fffffff;
    return (double)VERSAT_CONVERT(minusInf, float);
  }

  double extra = 0;
  while (val > MATH_E) {
    val /= MATH_E;
    extra += 1;
  }

  while (val < 1.0f) {
    val *= MATH_E;
    extra -= 1;
  }

  double res = (2.0 * Cordic_arctanh(val - 1, val + 1)) + extra;
  return res;
}

double Cordic_exp(double exponent) {
  int k = 4;
  double angle = exponent;
  double y = 1.207497067763;
  double x = 1.207497067763;
  double P2i = 0.5;

  int extra = 0;
  while (angle > 1.0) {
    angle -= 1.0;
    extra += 1;
  }

  while (angle < 0) {
    angle += 1.0;
    extra -= 1;
  }

  for (int i = 1; i < MAX_ITERS; i++) {
    double arc_tangent = thetah_table[i - 1];

    int iters = 1;
    if (i == k) {
      iters = 2;
      k = (3 * k) + 1;
    }

    for (int k = 0; k < iters; k++) {
      double sigma = 1.0;
      if (angle > 0.0) {
        sigma = -1.0;
      }

      angle = angle + sigma * arc_tangent;
      double calcX = x - sigma * y * P2i;
      double calcY = y - sigma * x * P2i;

      x = calcX;
      y = calcY;
    }

    P2i /= 2.0;
  }

  for (int i = 0; i < extra; i++) {
    x *= MATH_E;
  }
  for (int i = 0; i > extra; i--) {
    x /= MATH_E;
  }

  return x;
}

double Cordic_pow(double b, double e) {
  double result = Cordic_exp(e * Cordic_log(b));
  return result;
}

u32 LogCalculateIndex(UnpackedFP unpacked) {
  // Hardcoded for a fractional precision of 12
  u32 fracIndex = (unpacked.mantissa >> 11);

  return fracIndex;
}

double Table_log(double in) {
  UnpackedFP unpacked = Unpack(in, false);

  float exp = (float)unpacked.exponent;
  u32 fracIndex = LogCalculateIndex(unpacked);

  float logMantissa = logMantissaTable[fracIndex];
  float result = exp * VERSAT_CONVERT(log2Val, float) + logMantissa;

  return result;
}

double Table_exp(double exponent) {
  float data = exponent;

  int expPrecision = 8;
  int halfExpPrecision = expPrecision - 1;
  int expMax = (1 << halfExpPrecision) - 1;

  // Hardware unit that calculates real part and also returns a floating point
  // "view" of the real part.
  int asInteger = (int)data;
  int realPart = asInteger;
  if (realPart >= expMax) {
    realPart = expMax;
  }
  if (realPart <= -expMax) {
    realPart = -expMax;
  }

  bool isNegative = false;
  if (data < 0.0) {
    realPart = -realPart;
    isNegative = true;
    data = -data;
  }

  // NOTE: If the realPart goes is outside the [-127,127] range, then
  //       we do not actually care about the fractional part since we are in the
  //       range of infinity anyway.

  // Should be between 0 and 1
  float asFraction = data - (float)realPart;
  u32 mantissaPartU32 = *((u32 *)&asFraction);

  UnpackedFP unpacked = Unpack(asFraction, true);

  // Hardware unit that performs this calculation and outputs the fracIndex.
  u32 fracIndex = (unpacked.mantissa >>
                   (8 + (16 - EXP_MANTISSA_PRECISION) - unpacked.exponent)) &
                  ((1 << EXP_MANTISSA_PRECISION) - 1);
  u32 expIndex = realPart + (isNegative ? 128 : 0);

  if (isNegative) {
    fracIndex += (1 << EXP_MANTISSA_PRECISION);
  }

  float exp = expTable[expIndex];
  float frac = expMantissaTable[fracIndex];

  float res = exp * frac;

  return res;
}

double Table_pow(double base, double power) {
  double result = Table_exp(power * Table_log(base));
  return result;
}

double Taylor_log(double in) {
  double start = 0.0;

  for (int i = 0; i < 1000; i++) {
    double last = start;
    start = start + 2.0 * ((in - Taylor_exp(start)) / (in + Taylor_exp(start)));
    if (last == start) {
      break;
    }
  }

  return start;
}

double Taylor_exp(double exponent) {
  double result = 1.0;
  double term = 1.0;
  double div = 1.0;
  int maxTerms = 100000; // Failsafe

  double lastResult = result;
  for (int n = 1; n < maxTerms; n++) {
    term *= exponent / div;
    div += 1.0;
    result += term;

    // As term gets smaller eventually we will reach a point where addition does
    // not change anything
    if (lastResult == result) {
      break;
    }
    lastResult = result;
  }

  return result;
}

double Taylor_pow(double base, double power) {
  double result = Taylor_exp(power * Taylor_log(base));
  return result;
}

#if !EMBED_TABLES
uint32_t *expMantissaTable;
uint32_t *expTable;
uint32_t *logMantissaTable;
#endif

#include <stdlib.h>

void Versat_Init() {
  // Careful on this amount. Any more than this and the Alexnet test runs out of
  // memory.
  arena->allocated = 1024 * 1024 * 24;

#if VERSAT_AI_USE_TESTER
  arena->mem = (char *)0x01000000; // malloc(arena->allocated);
#else
  arena->mem = (char *)malloc(arena->allocated);
#endif

  storedProfiles = malloc(sizeof(ProfileSample) * 1000);
  maxProfiledSamples = 1000;

  // versat_printf("Arena %p - %p\n", arena->mem, arena->mem +
  // arena->allocated);

#if !EMBED_TABLES
  {
    logMantissaTable =
        (uint32_t *)malloc(sizeof(uint32_t) * LOG_MANTISSA_TABLE_SIZE);

    u32 increment =
        0x00000800; // TODO: Hardcoded for a fractionalPrecision of 12
    float f = 1.0f;
    for (int i = 0; i < LOG_MANTISSA_TABLE_SIZE; i++) {
      float val = Cordic_log(f);
      logMantissaTable[i] = VERSAT_CONVERT(val, u32);

      u32 asU32 = VERSAT_CONVERT(f, u32);
      asU32 += increment;
      f = VERSAT_CONVERT(asU32, float);
    }
  }

  {
    expTable = (uint32_t *)malloc(sizeof(uint32_t) * EXP_TABLE_SIZE);

    int halfSize = EXP_TABLE_SIZE / 2;

    float f = 0.0f;
    for (int i = 0; i < halfSize; i++) {
      float posExp = Cordic_exp(f);
      float negExp = Cordic_exp(-f);

      expTable[i] = VERSAT_CONVERT(posExp, u32);
      expTable[i + halfSize] = VERSAT_CONVERT(negExp, u32);
      f += 1.0f;
    }
  }

  {
    expMantissaTable =
        (uint32_t *)malloc(sizeof(uint32_t) * EXP_MANTISSA_TABLE_SIZE);

    float incr = 1.0 / (float)(1 << EXP_MANTISSA_PRECISION);
    float p = incr;

    float oneVal = 1.0f;

    expMantissaTable[0] = VERSAT_CONVERT(oneVal, u32);
    expMantissaTable[(1 << EXP_MANTISSA_PRECISION)] =
        VERSAT_CONVERT(oneVal, u32);

    for (int i = 1; i < (1 << EXP_MANTISSA_PRECISION); i++) {
      float posExp = Cordic_exp(p);
      float negExp = Cordic_exp(p);

      expMantissaTable[i] = VERSAT_CONVERT(posExp, u32);
      expMantissaTable[i + (1 << EXP_MANTISSA_PRECISION)] =
          VERSAT_CONVERT(negExp, u32);
      p += incr;
    }
  }
#endif
}

// Profiling
void _ProfileScope(int index, const char *name) {
  if (profileIndex >= maxProfiledSamples) {
    return;
  }

  storedProfiles[profileIndex].name = name;
  storedProfiles[profileIndex].time = versat_time();
  profileIndex += 1;
}

ProfileResult Profile_Get() {
  ProfileResult res = {};
  res.samples = storedProfiles;
  res.amount = profileIndex;
  return res;
}

void Profile_Reset() { profileIndex = 0; }

#if EMBED_TABLES
#define VERSAT_DO_EMBED_TABLES
#include "versat_embed_tables.h"

uint32_t *expMantissaTable = expMantissaTableArray;
uint32_t *expTable = expTableArray;
uint32_t *logMantissaTable = logMantissaTableArray;
#endif
