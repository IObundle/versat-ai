#ifndef INCLUDED_VERSAT_AI
#define INCLUDED_VERSAT_AI

#include <stddef.h>
#include <stdint.h>

#include "versat_ai_conf.h"

// ===============================
//  Global configurations
//

#if PC
#undef VERSAT_AI_USE_TESTER
#define VERSAT_AI_USE_TESTER 0
#endif

#define EMBED_TABLES 1
#define COMPUTE_TABLES 0

#define USE_ETHERNET 1
#define DEBUG 1

#define USE_CORDIC 1
#define USE_TABLE 0
#define USE_TAYLOR 0

#define VERSAT_OFFSET_PTR(PTR, OFFSET) ((void *)(((char *)PTR) + OFFSET))
#define VERSAT_CONVERT(IN, TYPE) (*((TYPE *)&IN))

// ==================
// Derived configs
//

#if !EMBED_TABLES && !COMPUTE_TABLES
#define EMPTY_TABLES 1
#else
#define EMPTY_TABLES 0
#endif

#if PC
#undef USE_ETHERNET
#endif

// ==================
// Config checking
//

#ifndef PC
#define PC 0
#endif

#if EMBED_TABLES && COMPUTE_TABLES
#error Cannot have embed tables and compute tables at the same time
#endif

#if USE_TABLE && !(EMBED_TABLES || COMPUTE_TABLES)
#error USE_TABLE defined but no table is being computed
#endif

#if USE_CORDIC && (USE_TABLE || USE_TAYLOR)
#error Multiple implementations being defined for math operations
#endif
#if USE_TABLE && (USE_CORDIC || USE_TAYLOR)
#error Multiple implementations being defined for math operations
#endif
#if USE_TAYLOR && (USE_CORDIC || USE_TABLE)
#error Multiple implementations being defined for math operations
#endif
#if !USE_TAYLOR && !USE_CORDIC && !USE_TABLE
#error No implementation selected for math operations
#endif

// NOTE: All these functions are used to set Versat specific functions that are
// defined by the firmware
//       All of them return the previously set function and by default they are
//       initialized with dummy functions that do not perform any action

// TODO: Maybe change the name since they are not actually used by Versat.

// Mandatory. The fuctions below are technically optional but this one must be
// called before any Inference function
void Versat_Init();

// Call this function with a valid function that is fast and returns some form
// of time measurement (application specific, Versat does not care about this
// result)
typedef uint64_t (*MeasureTimeFunction)();
MeasureTimeFunction Versat_SetTimeMeasurementFunction(MeasureTimeFunction func);

typedef void (*TimeResetFunction)();
TimeResetFunction Versat_SetTimeReset(TimeResetFunction func);

// Clear cache starting from ptr and spaning size bytes
// Depending on the architecture of the embedded system this might not be
// required or it might be essential.
typedef void (*ClearCache)(void *ptr, size_t size);
ClearCache Versat_SetClearCache(ClearCache func);

typedef int (*VersatPrintf)(const char *format, ...);

// Profiling
typedef struct {
  const char *name;
  union {
    uint64_t time;
    uint8_t asByte[8];
  };
} ProfileSample;

typedef struct {
  ProfileSample *samples;
  int amount;
} ProfileResult;

#define ProfileScope(INDEX, NAME) // _ProfileScope(INDEX, NAME)
void _ProfileScope(int index, const char *name);

ProfileResult Profile_Get();
void Profile_Reset();

// TODO: Still need to figure out how to make this work, we could just allocate
// some output memory and store the array inside it.
typedef struct {
  int numberOfOutputs;
  void **outputLocation; // outputLocation[N] gives the address of the N output.
} InferenceOutput;

typedef InferenceOutput (*InferenceFunction)(void *outputMemory,
                                             void *temporaryMemory,
                                             void **inputs, void *modelMemory);

typedef InferenceOutput (*DebugInferenceFunction)(void *outputMemory,
                                                  void *temporaryMemory,
                                                  void **inputs,
                                                  void *modelMemory,
                                                  void *correctInput);

// Numbers must match with the onnx script convention
// TODO: Better have onnx python script generate this to ensure they match
#define SourceType_OUTPUT_MEM 0
#define SourceType_TEMP_MEM 1
#define SourceType_INPUT 2
#define SourceType_MODEL_MEM 3
#define SourceType_CORRECT_MEM 4

typedef struct {
  uint32_t type;

  union {
    uint32_t memOffset;
    uint32_t inputIndex;
  };
} DataSource;

void DataSource_Print(DataSource source);

typedef struct {
  uint32_t operatorSize;

  uint32_t type;
  uint32_t useSoftware;
  float precision;
  DataSource output;

  uint32_t outputSize;
  DataSource correctOutput;

  uint32_t nInputs;
  DataSource inputs[];

  // Followed by operation info (of variable size)
} Operation;

void *Operation_GetOperationInfo(Operation *op);
void Operation_Print(Operation *op);

/*
  A compiled model is a variable sized list of variable sized operations.
*/

typedef struct {
  uint32_t outputSize;
  uint32_t tempSize;
  uint32_t modelSize;
  uint32_t correctSize;
  uint32_t totalInputSize;

  uint32_t inputCount;

  uint32_t nOperations;

  // Followed by:
  // uint32_t inputOffset[inputCount];
  // Operation operations[nOperations];
} CompiledModel;

static uint32_t *CompiledModel_InputOffsets(CompiledModel *model) {
  return (uint32_t *)&model[1];
}

static Operation *CompiledModel_Operations(CompiledModel *model) {
  uint32_t *inputOffsets = CompiledModel_InputOffsets(model);
  Operation *res = (Operation *)VERSAT_OFFSET_PTR(
      inputOffsets, sizeof(uint32_t) * model->inputCount);
  return res;
}

InferenceOutput RunCompiledInference(CompiledModel *model, void *outputMemory,
                                     void *temporaryMemory, void **inputs,
                                     void *modelMemory, void *correctInput);

// TODO: Remember, we do not want to force user to have to deal with this stuff
// at runtime (unless it is mandatory somewhat).
//       We want stuff to be inside defines and compile time expressions so that
//       user side can instantiate this stuff at compile time if needed. Even
//       when implementing models with parameters, we want to use function
//       defines rather than force user to calculate this stuff at compile time.
typedef struct {
  int outputSize;
  int tempSize;
  int modelSize;
  int correctSize;
  int totalInputSize;

  const char *nameSpace;

  int inputCount;
  const int *inputSizes;
  const int *inputOffsets;

  int operatorCount;

  // Set after calling any InferenceFunction (DebugInferenceFunction does not
  // set this) Measurements are in the form x[i] = time(); layerI(); x[i+1] =
  // time(); Meaning that in order to calculate the time taken by layerI we need
  // to calculate x[i+1] - x[i] afterwards Also meaning that we have
  // (operatorCount + 1) total measurements.
  uint64_t *timeMeasurements;

  InferenceFunction softwareInferenceFunction;
  InferenceFunction versatInferenceFunction;
  DebugInferenceFunction debugInferenceFunction;
} TestModelInfo;

#endif // INCLUDED_VERSAT_AI
