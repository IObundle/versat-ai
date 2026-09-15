#ifndef VERSAT_PRIVATE_INCLUDED
#define VERSAT_PRIVATE_INCLUDED

#include "versat_ai.h"

#include <stdbool.h>
#include <stddef.h>

// ======================================
// Global stuff (versat side)

extern VersatPrintf versat_printf;
extern MeasureTimeFunction versat_time;
extern ClearCache versat_clearCache;

#define EXP_MANTISSA_PRECISION 12
#define LOG_MANTISSA_PRECISION 12

#define EXP_MANTISSA_TABLE_SIZE (1 << (EXP_MANTISSA_PRECISION + 1))
#define EXP_TABLE_SIZE (256)
#define LOG_MANTISSA_TABLE_SIZE (1 << LOG_MANTISSA_PRECISION)

extern uint32_t *expMantissaTable;
extern uint32_t *expTable;
extern uint32_t *logMantissaTable;

static int32_t log2Val = 0x3f317218;

typedef struct Arena_t {
  void *mem;
  int used;
  int allocated;
} Arena;

extern Arena *arena;

// ======================================
// Dimensions
#define MAX_DIMS 6

typedef struct {
  int64_t data[MAX_DIMS];
  int size;
} Dimensions;

Dimensions CreateDimensions(int64_t *dims, int numberDims);
void Dimensions_PrependInPlace(
    Dimensions *dim, int value); // A bit slow, do not abuse if possible
void Dimensions_AppendInPlace(Dimensions *dim, int value);

Dimensions Dimensions_Cut_GetLeft(Dimensions dim, int amount);
Dimensions Dimensions_Cut_GetRight(Dimensions dim, int amount);

int Dimensions_TotalSize(Dimensions dim);

// ======================================
// AddressGen

typedef struct {
  int offsetAddressVars[MAX_DIMS];
  int addressVars[MAX_DIMS];
  int64_t properDims[MAX_DIMS];

  int64_t iterationDims[MAX_DIMS];
  int numberDims;
} AddressGen;

AddressGen StartAddress(int64_t *iterationDims, int64_t *properDims,
                        int numberDims);

// If dims is A x B x C and iterDims = 1 then A is iterated and B x C are not
// iterated. If iterDims = 2 then A x B are iterated and C is not and so on.
// iterDims = 0 means no iteration.
AddressGen StartAddressFromDims(Dimensions dims, int iterDims);

int Address_GetDim(AddressGen *gen, int index);
void Address_Print(AddressGen *gen);
int Address_GetValue(AddressGen *gen);
bool Address_IsValid(AddressGen *gen);
void Address_Advance(AddressGen *gen);
void Address_AdvanceAxis(AddressGen *gen, int axisToAdvance);
void Address_Restart(AddressGen *gen);

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
KernelGen StartKernel_IterateOneDimOnly(AddressGen *address, int dimToIterate,
                                        int start, int end);

void Kernel_PrintShort(KernelGen *gen);
void Kernel_Print(KernelGen *gen);
int Kernel_GetValue(KernelGen *gen);
bool Kernel_IsValid(KernelGen *gen);
bool Kernel_IsInsidePad(KernelGen *gen);
void Kernel_Advance(KernelGen *gen);

// ======================================
// Arena (Temporary)
// TODO: All arena stuff eventually must be removed. Do not want to allocate
// stuff mid inference if possible.

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
  uint32_t outputSize;
} LayerInfo;

#include "versat_ai_operators_meta.h"

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
void *Software_BatchNormalization(void *inputX, void *scale, void *inputB,
                                  void *mean, void *var, void *output,
                                  int index, BatchNormalizationInfo *info);
void *Software_Dropout(void *input, void *out, int index, DropoutInfo *info);
void *Software_LRN(void *input, void *out, int index, LRNInfo *info);
void *Software_Gemm(void *inA, void *inB, void *inC, void *out, int index,
                    GemmInfo *info);
void *Software_Pad(void *inA, void *out, int index, PadInfo *info);
void *Software_FixPad(void *inA, void *out, int index, FixPadInfo *info);

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
void *Versat_BatchNormalization(void *inputX, void *scale, void *inputB,
                                void *mean, void *var, void *output, int index,
                                BatchNormalizationInfo *info);
void *Versat_Dropout(void *input, void *out, int index, DropoutInfo *info);
void *Versat_LRN(void *input, void *out, int index, LRNInfo *info);
void *Versat_Gemm(void *inA, void *inB, void *inC, void *out, int index,
                  GemmInfo *info);

// ======================================
// Misc

int64_t CalculateSizeOfDim(int64_t *dim, int dims);

void AssertAlmostEqual(void *toTest, void *correctValues, int index,
                       float precision, LayerInfo *info);

float my_invsqrt(float number);

void silent_clear_cache();

void PrintTime(uint64_t start);

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

  int advanceX;
  int advanceY;
  int advanceC;

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
  // TODO: The comment below is technically true but we might want to represent
  // inputSizeC because of groups.
  //       We might be able to push the logic of conv groups
  // NOTE: Versat cannot handle processing less than full input channels per
  // run.
  //       Otherwise we would need to store the "half sum" somewhere and
  //       add everything together at the end

  int outputC;
  int outputSizeC;

  int actualKernelW;
  int actualKernelH;

  int kernelStartW;
  int kernelStartH;

  int outputW;
  int outputH;

  PaddingRegion padding;
  bool entireWindowInsidePadding;
} AdvancedWindow;

WindowGen StartWindowGen(ExtraInfo *info, bool iterateC, bool isNCHW);
WindowGen StartAdvancedWindowGen(ExtraInfo *info, bool iterateC, bool isNCHW,
                                 int xMaxAdvance, int yMaxAdvance,
                                 int cMaxAdvance);

AdvancedWindow WindowGen_Get(WindowGen *gen);
void WindowGen_GetTruePadding(WindowGen *gen, AdvancedWindow *out);
void WindowGen_Advance(WindowGen *gen);
void WindowGen_AdvanceTruePadding(WindowGen *gen, AdvancedWindow w);

bool WindowGen_Valid(WindowGen *gen);

void AdvancedWindow_Print(AdvancedWindow window);

// ======================================
// Tensor

Tensor CreateTensor_NoAllocate(int64_t *dims, int numberDims);
int Tensor_Size(Tensor tensor);
void Tensor_Print(Tensor tensor);

// ======================================
// Math

double Cordic_log(double in);
double Cordic_exp(double exponent);
double Cordic_pow(double base, double power);

double Table_log(double in);
double Table_exp(double exponent);
double Table_pow(double base, double power);

double Taylor_log(double in);
double Taylor_exp(double exponent);
double Taylor_pow(double base, double power);

#if USE_CORDIC
#define SOFT_LOG(X) Cordic_log(X)
#define SOFT_EXP(X) Cordic_exp(X)
#define SOFT_POW(B, E) Cordic_pow(B, E)
#endif

#if USE_TABLE
#define SOFT_LOG(X) Table_log(X)
#define SOFT_EXP(X) Table_exp(X)
#define SOFT_POW(B, E) Table_pow(B, E)
#endif

#if USE_TAYLOR
#define SOFT_LOG(X) Taylor_log(X)
#define SOFT_EXP(X) Taylor_exp(X)
#define SOFT_POW(B, E) Taylor_pow(B, E)
#endif

#endif // VERSAT_PRIVATE_INCLUDED
