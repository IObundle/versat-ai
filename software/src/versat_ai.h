#ifndef INCLUDED_VERSAT_AI
#define INCLUDED_VERSAT_AI

#include <stddef.h>
#include <stdint.h>

// NOTE: All these functions are used to set Versat specific functions that are
// defined by the firmware
//       All of them return the previously set function and by default they are
//       initialized with dummy functions that do not perform any action

// Call this function with a valid function that is fast and returns some form
// of time measurement (application specific, Versat does not care about this
// result)
typedef uint64_t (*MeasureTimeFunction)();
MeasureTimeFunction Versat_SetTimeMeasurementFunction(MeasureTimeFunction func);

// Versat will not print any debug messages unless this is set beforehand.
typedef int (*PrintFunction)(const char *name, ...);
PrintFunction Versat_SetPrintFunction(PrintFunction func);

// Clear cache starting from ptr and spaning size bytes
// Depending on the architecture of the embedded system this might not be
// required or it might be essential.
typedef void (*ClearCache)(void *ptr, size_t size);
ClearCache Versat_SetClearCache(ClearCache func);

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
