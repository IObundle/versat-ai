#ifndef VERSAT_PRIVATE_INCLUDED
#define VERSAT_PRIVATE_INCLUDED

#include "versat_ai.h"

#include <stdbool.h>
#include <stddef.h>

#define OFFSET_PTR(PTR, OFFSET) ((void *)(((char *)PTR) + OFFSET))

// ======================================
// Global stuff (versat side)

extern MeasureTimeFunction versat_time;
extern PrintFunction versat_printf;
extern ClearCache versat_clearCache;

// ======================================
// Dimensions
#define MAX_DIMS 6

typedef struct {
  int64_t data[MAX_DIMS];
  int size;
} Dimensions;

Dimensions CreateDimensions(int64_t *dims, int numberDims);
int Dimensions_Size(Dimensions dim);

// ======================================
// AddressGen

typedef struct {
  int offsetAddressVars[MAX_DIMS];
  int addressVars[MAX_DIMS];
  int64_t properDims[MAX_DIMS];

  int64_t iterationDims[MAX_DIMS];
  int numberDims;
} AddressGen;

void Address_Print(AddressGen *gen);
int Address_GetValue(AddressGen *gen);
bool Address_IsValid(AddressGen *gen);
void Address_Advance(AddressGen *gen);
void Address_AdvanceAxis(AddressGen *gen, int axisToAdvance);
AddressGen StartAddress(int64_t *iterationDims, int64_t *properDims,
                        int numberDims);

AddressGen Address_Map(AddressGen *in, int64_t *biggerDim, int *stride);

// TODO: Need to standardize this stuff eventually.
AddressGen Address_Map2(AddressGen *in, int64_t *biggerDim, int *stride,
                        int *offset);

// ======================================
// KernelGen

/*
  A Kernel gen is basically a subiterator that starts from the position on the
  parent AddressGen and iterates a subsection of a subsection of the dimensions.

  If we have an AddressGen that iterates over A,B,C,D then as an example we can
  create a KernelGen that iterates over C,D and the iteration can be bounded to
  a smaller "rectangle" like a 3x3 area over the C,D dimensions. Note that the
  KernelGen always starts from the AddressGen position. Furthermore, because the
  KernelGen can "escape" over the given dimensions, we provide a
  Kernel_IsInsidePad that returns true if the KernelGen is outside the
  boundaries of the provided dimensions. In this case the Kernel_GetValue
  function returns garbage and should not be used.

  TODO: We probably can augment the AddressGen struct to support this usecase
  so that we can return an AddressGen struct that returns the same indexes
  that this would return. I do not think there is a need to have a separate
  struct for this, altough not sure about it.
*/

typedef struct {
  int kernelVars[MAX_DIMS]; // Current state

  // Kernel Info
  // AddressGen *address;
  int addressGenVars[MAX_DIMS]; // The value of the address vars at the start of
                                // the kernel iteration.
  int addressIterDims[MAX_DIMS];   // The original iteration dimensions. Kernel
                                   // does not iterate outside of the original
                                   // address gen space.
  int addressProperDims[MAX_DIMS]; // The original dimensions. Need to figure
                                   // out if we are inside pad or not.

  int kernelDims[MAX_DIMS];
  int kernelDilations[MAX_DIMS]; // NOTE: Not properly tested, do not rely on
                                 // dilations being correct
  int numberDims;
} KernelGen;

KernelGen StartKernel(AddressGen *address, int *kernelDims, int kernelSize);
void Kernel_PrintShort(KernelGen *gen);
void Kernel_Print(KernelGen *gen);
int Kernel_GetValue(KernelGen *gen);
bool Kernel_IsValid(KernelGen *gen);
bool Kernel_IsInsidePad(KernelGen *gen);
void Kernel_Advance(KernelGen *gen);

// ======================================
// Arena (Temporary)
// TODO: All arena stuff eventually must be removed. Do not want to allocate
// stuff mid inference.

struct Arena_t;
typedef struct Arena_t Arena;

// ======================================
// Tensor stuff that depends on Arena (Temporary)
typedef struct {
  Dimensions dims;
  float *data;
} Tensor;

// NOTE: Very important. We are currently allocating stuff but we will
// eventually remove all the memory allocations and push them to outside this
// code. We want to offer a very simple "allocate x amount of space before
// starting our code" model of usage since this is intented to run on embedded
// targets.
Tensor PushTensor(Arena *out, int64_t *dims, int numberDims);
Tensor CreateTensor_NoAllocate(int64_t *dims, int numberDims);
Tensor Tensor_Transpose(Tensor in, int *index, Arena *out);

void Address_Print(AddressGen *gen);
int Address_GetValue(AddressGen *gen);
bool Address_IsValid(AddressGen *gen);
void Address_Advance(AddressGen *gen);
void Address_AdvanceAxis(AddressGen *gen, int axisToAdvance);
AddressGen StartAddress(int64_t *iterationDims, int64_t *properDims,
                        int numberDims);

// ======================================
// Layers

typedef struct {
  const char *typeName;
  size_t outputSize;
} LayerInfo;

typedef struct {
  // Extra info to help
  int maxDims;
  int64_t *firstInputDim;
  int64_t *secondInputDim;
  int64_t *broadCastedShape;
} AddInfo;

typedef struct {
  int dims;
  int64_t *inputDims;
} ReluInfo;

typedef enum {
  PaddingType_NOTSET,
  PaddingType_SAME_UPPER,
  PaddingType_SAME_LOWER,
  PaddingType_VALID
} PaddingType;

typedef struct {
  int dims;
  int64_t *inputDims;
  int64_t *outputDims;
  int kernelSize;
  int *kernelDims;
  int strideSize;
  int *strideDims;
  PaddingType padding;
  int padsSize;
  int *padsDims;
} MaxPoolInfo;

typedef struct {
  int dims;
  int64_t *inputDims;
  int64_t *outputDims;
  int kernelSize;
  int *kernelDims;
  int strideSize;
  int *strideDims;
  PaddingType padding;
  int padsSize;
  int *padsDims;
} AveragePoolInfo;

typedef struct {
  int dims;
  int64_t *inputDims;
  int64_t *outputDims;
  int featureMaps;
  int kernelSize;
  int *kernelDims;
  int strideSize;
  int *strideDims;
  int dilationsSize;
  int *dilationsDims;
  PaddingType padding;
  int padsSize;
  int *padsDims;
  int group;
} ConvInfo;

typedef struct {
  int64_t *inputDims;
  int numberInputDims;
  int numberShapeDims;
} ReshapeInfo;

typedef struct {
  int64_t *inputADims;
  int numberInputADims;
  int64_t *inputBDims;
  int numberInputBDims;
  int64_t *outputDims;
  int numberOutputDims;
} MatMulInfo;

typedef struct {
  int64_t *inputDims;
  int numberInputDims;
  int axis;
} SoftmaxInfo;

typedef struct {
  int64_t *inputDims;
  int numberInputDims;
  int64_t *perm;
  int permSize;
} TransposeInfo;

// Software implementations
void *Software_Conv(void *inputX, void *inputW, void *output, int index,
                    ConvInfo *info);
void *Software_ConvWithBias(void *inputX, void *inputW, void *inputB,
                            void *output, int index, ConvInfo *info);
void *Software_Reshape(void *data, void *shape, void *output, int index,
                       ReshapeInfo *info);
void *Software_Transpose(void *inputA, void *output, int index,
                         TransposeInfo *info);
void *Software_Add(void *inputA, void *inputB, void *output, int index,
                   AddInfo *info);
void *Software_Relu(void *inputX, void *output, int index, ReluInfo *info);
void *Software_MaxPool(void *inputX, void *output, int index,
                       MaxPoolInfo *info);
void *Software_AveragePool(void *inputX, void *output, int index,
                           AveragePoolInfo *info);
void *Software_MatMul(void *inputA, void *inputB, void *output, int index,
                      MatMulInfo *info);
void *Software_Softmax(void *inputA, void *output, int index,
                       SoftmaxInfo *info);

// Accelerator implementations
void *Versat_Add(void *inputA, void *inputB, void *output, int index,
                 AddInfo *info);

void *Versat_Relu(void *inputA, void *output, int index, ReluInfo *info);

void *Versat_Reshape(void *data, void *shape, void *output, int index,
                     ReshapeInfo *info);
void *Versat_MaxPool(void *inputX, void *output, int index, MaxPoolInfo *info);
void *Versat_AveragePool(void *inputX, void *output, int index,
                         AveragePoolInfo *info);
void *Versat_Conv(void *inputX, void *inputW, void *output, int index,
                  ConvInfo *info);
void *Versat_ConvWithBias(void *inputX, void *inputW, void *inputB,
                          void *output, int index, ConvInfo *info);
void *Versat_MatMul(void *inputA, void *inputB, void *output, int index,
                    MatMulInfo *info);
void *Versat_Softmax(void *inputA, void *output, int index, SoftmaxInfo *info);

// ======================================
// Misc

int64_t CalculateSizeOfDim(int64_t *dim, int dims);

void AssertAlmostEqual(void *toTest, void *correctValues, int index,
                       LayerInfo *info);

// ======================================
// Extra Info

typedef struct {
  int strideW;
  int strideH;

  int kernelW;
  int kernelH;

  int inputImageW;
  int inputImageH;
  int inputImageC;

  int outputImageW;
  int outputImageH;
  int outputImageC;

  int leftPadW;
  int leftPadH;
  int rightPadW;
  int rightPadH;

  int padW;
  int padH;
} ExtraInfo;

void ExtraInfo_Print(ExtraInfo e);

ExtraInfo CalculateExtraInfo_MaxPool(MaxPoolInfo *info);
ExtraInfo CalculateExtraInfo_AveragePool(AveragePoolInfo *info);
ExtraInfo CalculateExtraInfo_Conv(ConvInfo *info);

// ======================================
// WindowGen

typedef struct {
  ExtraInfo *info;
  int currentOutputC;
  int currentOutputX;
  int currentOutputY;
  bool iterateC;
  bool isNCHW; // Otherwise assume it is NHWC
} WindowGen;

typedef enum {
  PaddingRegion_TOP = (1 << 1),
  PaddingRegion_LEFT = (1 << 2),
  PaddingRegion_RIGHT = (1 << 3),
  PaddingRegion_BOTTOM = (1 << 4)
} PaddingRegion;

typedef struct {
  int inputX;
  int inputY;
  int outputX;
  int outputY;

  int startC;
  int inputSizeC; // This is mostly the same as inputImageC since Conv cannot
                  // handle half sums. We must always process the entire input
                  // channels, we cannot handle half sums.

  int outputC;
  int outputSizeC;

  int actualKernelW;
  int actualKernelH;

  int kernelStartW;
  int kernelStartH;

  int outputW;
  int outputH;

  PaddingRegion padding;
} AdvancedWindow;

WindowGen StartWindowGen(ExtraInfo *info, bool iterateC, bool isNCHW);
AdvancedWindow WindowGen_Get(WindowGen *gen);
void WindowGen_Advance(WindowGen *gen);
bool WindowGen_Valid(WindowGen *gen);

void AdvancedWindow_Print(AdvancedWindow window);

// ======================================
// Tensor

Tensor CreateTensor_NoAllocate(int64_t *dims, int numberDims);
int Tensor_Size(Tensor tensor);
void Tensor_Print(Tensor tensor);

#endif // VERSAT_PRIVATE_INCLUDED
