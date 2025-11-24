#include "versat_private.h"

#define MAX(A, B) ((A) > (B) ? (A) : (B))

// ======================================
// Global stuff (versat side)

uint64_t Versat_DefaultMeasureTime() { return 0; }
int Versat_DefaultPrintFunction(const char *name, ...) { return 0; }
void Versat_DefaultClearCache(void *ptr, size_t size) {}

MeasureTimeFunction versat_time = Versat_DefaultMeasureTime;
PrintFunction versat_printf = Versat_DefaultPrintFunction;
ClearCache versat_clearCache = Versat_DefaultClearCache;

MeasureTimeFunction
Versat_SetTimeMeasurementFunction(MeasureTimeFunction func) {
  MeasureTimeFunction old = versat_time;
  versat_time = func;
  return old;
}

PrintFunction Versat_SetPrintFunction(PrintFunction func) {
  PrintFunction old = versat_printf;
  versat_printf = func;
  return old;
}

ClearCache Versat_SetClearCache(ClearCache func) {
  ClearCache old = versat_clearCache;
  versat_clearCache = func;
  return old;
}

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

int Dimensions_Size(Dimensions dim) {
  int size = 1;
  for (int i = 0; i < dim.size; i++) {
    size *= dim.data[i];
  }
  return size;
}

// ======================================
// Address

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
    versat_printf("%ld", gen->kernelDims[i]);
  }
  versat_printf("]\n");

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
                       LayerInfo *info) {
  float *test = (float *)toTest;
  float *correct = (float *)correctValues;

  size_t outputSize = info->outputSize / sizeof(float);

  versat_printf("Gonna check output of layer: %d\n", index);

  if (outputSize == 0) {
    versat_printf(
        "Error, AssertAlmostEqual with output size of 0. Should not be "
        "possible\n");
    return;
  }

  int maxIncorrect = 10;
  bool printOk = true;

  // Make sure that cache is not affecting the verification process
  // TODO: Proper boundaries
  versat_clearCache(NULL, 0);

  int incorrectFound = 0;
  for (int i = 0; i < outputSize; i++) {
    if (absf(correct[i] - test[i]) > 0.001f) {
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

  if (printOk && incorrectFound == 0) {
    versat_printf("[%s] (Layer %d) - OK\n", info->typeName, index);
  }
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

  res.strideW = info->strideDims[1];
  res.strideH = info->strideDims[0];

  res.kernelW = info->kernelDims[1];
  res.kernelH = info->kernelDims[0];

  res.inputImageW = info->inputDims[3];
  res.inputImageH = info->inputDims[2];
  res.inputImageC = info->inputDims[1];

  res.outputImageC = info->outputDims[1];
  res.outputImageH = info->outputDims[2];
  res.outputImageW = info->outputDims[3];

  if (info->padding == PaddingType_NOTSET) {
    // TODO: Need a better way of handling errors in this layer, I think.
    if (info->padsSize != 4) {
      versat_printf("ERROR, pads size is not expected");
      return (ExtraInfo){};
    }

    res.leftPadW = info->padsDims[1];
    res.leftPadH = info->padsDims[0];

    res.rightPadW = info->padsDims[3];
    res.rightPadH = info->padsDims[2];

    res.padW = info->padsDims[1] + info->padsDims[3];
    res.padH = info->padsDims[0] + info->padsDims[2];
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

  res.strideW = info->strideDims[1];
  res.strideH = info->strideDims[0];

  res.kernelW = info->kernelDims[1];
  res.kernelH = info->kernelDims[0];

  res.inputImageW = info->inputDims[3];
  res.inputImageH = info->inputDims[2];
  res.inputImageC = info->inputDims[1];

  res.outputImageC = info->outputDims[1];
  res.outputImageH = info->outputDims[2];
  res.outputImageW = info->outputDims[3];

  if (info->padding == PaddingType_NOTSET) {
    // TODO: Need a better way of handling errors in this layer, I think.

    if (info->padsSize != 4) {
      versat_printf("ERROR, pads size is not expected");
      return (ExtraInfo){};
    }

    res.leftPadW = info->padsDims[1];
    res.leftPadH = info->padsDims[0];

    res.rightPadW = info->padsDims[3];
    res.rightPadH = info->padsDims[2];

    res.padW = info->padsDims[1] + info->padsDims[3];
    res.padH = info->padsDims[0] + info->padsDims[2];
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

  res.strideW = info->strideDims[1];
  res.strideH = info->strideDims[0];

  res.kernelW = info->kernelDims[1];
  res.kernelH = info->kernelDims[0];

  res.inputImageW = info->inputDims[3];
  res.inputImageH = info->inputDims[2];
  res.inputImageC = info->inputDims[1];

  res.outputImageC = info->outputDims[1];
  res.outputImageH = info->outputDims[2];
  res.outputImageW = info->outputDims[3];

  if (info->padding == PaddingType_NOTSET) {
    // TODO: Need a better way of handling errors in this layer, I think.
    if (info->padsSize != 4) {
      versat_printf("ERROR, pads size is not expected");
      return (ExtraInfo){};
    }

    res.leftPadW = info->padsDims[1];
    res.leftPadH = info->padsDims[0];

    res.rightPadW = info->padsDims[3];
    res.rightPadH = info->padsDims[2];

    res.padW = info->padsDims[1] + info->padsDims[3];
    res.padH = info->padsDims[0] + info->padsDims[2];
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
  versat_printf("WindowSize (Out view): %d %d %d\n", window.outputSizeC,
                window.outputH, window.outputW);
  versat_printf("KernelSizeAndOffset: %d:%d - %d:%d\n", window.actualKernelW,
                window.kernelStartW, window.actualKernelH, window.kernelStartH);
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

  // For now, just like the rest of the window, we only advance a single output
  // channel
  res.outputSizeC = 1;

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

  return res;
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
