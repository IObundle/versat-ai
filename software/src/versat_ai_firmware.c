/*
 * SPDX-FileCopyrightText: 2025 IObundle
 *
 * SPDX-License-Identifier: MIT
 */

#include "versat_ai.h"

#if !VERSAT_AI_USE_TESTER

#include "iob_bsp.h"
#include "iob_printf.h"
#include "iob_timer.h"
#include "iob_uart.h"
#include "versat_accel.h"
#include "versat_ai_conf.h"
#include "versat_ai_mmap.h"
#include <string.h>

#if PC
#include <stdio.h>
#include <unistd.h> // for sleep()
long int GetFileSize(FILE *file) {
  long int mark = ftell(file);

  fseek(file, 0, SEEK_END);
  long int size = ftell(file);

  fseek(file, mark, SEEK_SET);

  return size;
}
#endif

void FastReceiveFile(const char *pathPrefix, const char *path, void *buffer,
                     int expectedSize) {
  char fullPath[128];
#if PC
  snprintf(fullPath, 128, "../resources/%s_%s", pathPrefix, path);
  FILE *f = fopen(fullPath, "r");
  if (!f) {
    printf("Problem opening file for reading: %s\n", fullPath);
    return;
  }

  long int size = GetFileSize(f);
  fread(buffer, sizeof(char), size, f);
  fclose(f);
  return;
#endif

  snprintf(fullPath, 128, "%s_%s", pathPrefix, path);
  uart_recvfile(fullPath, buffer);
  printf("Received file by uart\n");
}

void silent_clear_cache() {
#if !PC
  for (unsigned int i = 0; i < 10; i++)
    asm volatile("nop");
  // Flush VexRiscv CPU internal cache
  asm volatile(".word 0x500F" ::: "memory");
#endif
}

void silent_clear_cache_args(void *ptr, size_t size) { silent_clear_cache(); }

void clear_cache() {
#if !PC
  // Delay to ensure all data is written to memory
  printf("Gonna clear the cache\n");
  for (unsigned int i = 0; i < 10; i++)
    asm volatile("nop");
  // Flush VexRiscv CPU internal cache
  asm volatile(".word 0x500F" ::: "memory");
#endif
}

void *Align4(void *in) {
  iptr asInt = (iptr)in;

  asInt = ((asInt + 3) & ~3);
  return (void *)asInt;
}

void PrintTimeElapsed(const char *message, uint64_t start, uint64_t end) {
  uint64_t freqInMhz = IOB_BSP_FREQ / 1000000ull;

  uint64_t elapsed = (end - start) / freqInMhz;

  uint64_t secondsElapsed = elapsed / 1000000;
  uint64_t remainingTime = elapsed % 1000000;

  printf("%s: %d.%06d (@%dMHz)\n\n", message, (int)secondsElapsed,
         (int)remainingTime, IOB_BSP_FREQ / 1000000);
}

void PrintU64InHex(uint64_t n) {
  union {
    uint64_t u64;
    uint32_t u32[2];
  } conv;

  conv.u64 = n;

  printf("%08x%08x\n", conv.u32[1], conv.u32[0]);
}

typedef struct {
  void *data;
  uint32_t size;
} File;

void uart_sendstr(char *name);

uint32_t uart_filesize(char *file_name) {
  uart_puts(UART_PROGNAME);
  uart_puts(": requesting to get file size\n");

  // send file receive request
  uart_putc(0x09);

  // send file name
  uart_sendstr(file_name);

  // receive file size
  uint32_t file_size = uart_getc();
  file_size |= ((uint32_t)uart_getc()) << 8;
  file_size |= ((uint32_t)uart_getc()) << 16;
  file_size |= ((uint32_t)uart_getc()) << 24;

  uart_putc(ACK);

  return file_size;
}

File GetFile(const char *path) {
#if PC
  char fullPath[128];
  snprintf(fullPath, 128, "../resources/%s", path);
  FILE *f = fopen(fullPath, "r");
  if (!f) {
    printf("Problem opening file for reading: %s\n", fullPath);
    return (File){};
  }

  long int size = GetFileSize(f);
  void *data = malloc(size + 16);
  fread(data, sizeof(char), size, f);
  fclose(f);

  File res = {};
  res.data = data;
  res.size = size;

  return res;
#else
  uint32_t size = uart_filesize(path);
  void *data = malloc(size + 16);
  uart_recvfile(path, data);

  File res = {};
  res.data = data;
  res.size = size;

  return res;
#endif
}

static bool IsAlpha(char ch) {
  bool res = false;

  res |= (ch >= 'a' && ch <= 'z');
  res |= (ch >= 'A' && ch <= 'Z');
  res |= (ch >= '0' && ch <= '9');
  res |= (ch == '_');

  return res;
}

int main() {
  char pass_string[] = "Test passed!";
  char fail_string[] = "Test failed!";

  // init timer
  timer_init(TIMER0_BASE);

  // init uart
  uart_init(UART0_BASE, IOB_BSP_FREQ / IOB_BSP_BAUD);
  printf_init(&uart_putc);

  // test puts
  uart_puts("\n\n\nHello world from versat_ai!\n\n\n");

#ifdef TEST_NAME
  printf("\n\nRunning test %s\n\n", TEST_NAME);
#endif

  uart_puts("\nGonna init versat!\n");
  SetVersatDebugPrintfFunction(printf);
  versat_init(VERSAT0_BASE);

  ConfigCreateVCD(false);

  Versat_SetTimeReset(timer_reset);
  Versat_SetTimeMeasurementFunction(timer_get_count);
  Versat_SetClearCache(silent_clear_cache_args);
  Versat_Init();

  printf("Versat base: %x\n", VERSAT0_BASE);

#if DEBUG
  int stackVar;
  printf("Stack  : %p\n", &stackVar);
#endif

#if EMPTY_TABLES
  printf("\n\n[WARNING] Running without computing or embedding tables. Any "
         "operator that uses any transcendental functions should fail.\n\n");
#endif

  File metadata = GetFile("VERSAT_TEST_METADATA.txt");

  char *ptr = (char *)metadata.data;
  char *end = ptr + metadata.size;

  for (; ptr < end;) {
    if (!IsAlpha(*ptr)) {
      break;
    }

    char *lineStart = ptr;
    while (IsAlpha(*ptr)) {
      ptr += 1;
    }
    char *lineEnd = ptr;
    int size = lineEnd - lineStart;

    ptr = lineEnd + 1;

    char pathBuffer[256];
    sprintf(pathBuffer, "%.*s_metamodel.bin", size, lineStart);

    File metamodel = GetFile(pathBuffer);
    CompiledModel *compiledModel = (CompiledModel *)metamodel.data;

    printf("Output: %d\n", compiledModel->outputSize);
    printf("Temp: %d\n", compiledModel->tempSize);
    printf("Model: %d\n", compiledModel->modelSize);
    printf("Correct: %d\n", compiledModel->correctSize);
    printf("Input: %d\n", compiledModel->totalInputSize);

    char *workBuffer = (char *)malloc(400 * 1024 * 1024);

    // Allocate space for each memory buffer, +16 to give us some wiggle room.
    // Proper code should work without this but we will handle this later.
    char *output = workBuffer + metamodel.size + 16;
    char *temp = output + compiledModel->outputSize + 16;
    char *model = temp + compiledModel->tempSize + 16;
    char *correct = model + compiledModel->modelSize + 16;
    char *inputs = correct + compiledModel->correctSize + 16;

    printf("\n\n");
    printf("Output: %p\n", output);
    printf("Temp: %p\n", temp);
    printf("Model: %p\n", model);
    printf("Correct: %p\n", correct);
    printf("Input: %p\n", inputs);

    void **inputsVector = (void **)(inputs + compiledModel->totalInputSize);
    uint32_t *inputOffsets = CompiledModel_InputOffsets(compiledModel);
    for (int i = 0; i < compiledModel->inputCount; i++) {
      inputsVector[i] = VERSAT_OFFSET_PTR(inputs, inputOffsets[i]);
    }

    printf("Inputs Vector: %p\n", inputsVector);
    printf("Inputs Vector val: %p %p\n", inputsVector[0], inputsVector[1]);
    printf("\n\n");

    sprintf(pathBuffer, "%.*s", size, lineStart);

    FastReceiveFile(pathBuffer, "correctOutputs.bin", correct,
                    compiledModel->correctSize);
    FastReceiveFile(pathBuffer, "model.bin", model, compiledModel->modelSize);
    FastReceiveFile(pathBuffer, "inputs.bin", inputs,
                    compiledModel->totalInputSize);

    RunCompiledInference(compiledModel, output, temp, inputsVector, model,
                         correct);
  }

#if PC
  sleep(1);
#endif

  uart_sendfile("test.log", strlen(pass_string), pass_string);

  // read current timer count, compute elapsed time
  unsigned long long elapsed = timer_get_count();
  unsigned int elapsedu = elapsed / (IOB_BSP_FREQ / 1000000);

  PrintTimeElapsed("\nTotal time elasped", 0, elapsed);

  uart_finish();

  return 0;
}

#else // VERSAT_AI_USE_TESTER

#include "iob_bsp.h"
#include "iob_printf.h"
#include "versat_ai_conf.h"
#include "versat_ai_mmap.h"

#include "versat_accel.h"

#include <stdbool.h>
#include <stdint.h>

#include "iob_regfileif_inverted_csrs.h"
#include "iob_timer.h"
#include "iob_uart.h"

void silent_clear_cache() {
#if !PC
  for (unsigned int i = 0; i < 10; i++)
    asm volatile("nop");
  // Flush VexRiscv CPU internal cache
  asm volatile(".word 0x500F" ::: "memory");
#endif
}

void silent_clear_cache_args(void *ptr, size_t size) { silent_clear_cache(); }

void delayed_putc(char c) {
  for (unsigned int i = 0; i < 1000; i++)
    asm volatile("nop");
  uart_putc(c);
}

int main() {
  // init timer
  timer_init(TIMER0_BASE);

  // init uart
  uart_init(UART0_BASE, IOB_BSP_FREQ / IOB_BSP_BAUD);
  printf_init(&delayed_putc);

  printf("Gonna init versat\n");

  SetVersatDebugPrintfFunction(printf);
  versat_init(VERSAT0_BASE);
  ConfigCreateVCD(false);

  Versat_SetTimeReset(timer_reset);
  Versat_SetTimeMeasurementFunction(timer_get_count);
  Versat_SetClearCache(silent_clear_cache_args);
  Versat_Init();

  iob_regfileif_inverted_csrs_init_baseaddr(REGFILEIF0_BASE);

  printf("Sut initialized\n");

  while (1) {
    while (iob_regfileif_inverted_csrs_get_start() == 0)
      ;
    iob_regfileif_inverted_csrs_set_done(0);
    iob_regfileif_inverted_csrs_set_start(0);

    // Make sure that we are reading any values set by Tester correctly
    silent_clear_cache();

    printf("Inside SUT\n");
    printf("Inside SUT\n");
    printf("Inside SUT\n");
    printf("Inside SUT\n");
    printf("Inside SUT\n");
    printf("Inside SUT\n");
    printf("Inside SUT\n");
    printf("Inside SUT\n");
    printf("Inside SUT\n");

    void **recvData0 = (void **)0x02000000;
    void **recvData1 = (void **)0x02000004;
    void **recvData2 = (void **)0x02000008;
    void **recvData3 = (void **)0x0200000c;
    void **recvData4 = (void **)0x02000010;
    void **recvData5 = (void **)0x02000014;

    CompiledModel *compiledModel = (CompiledModel *)*recvData0;
    char *output = (char *)*recvData1;
    char *temp = (char *)*recvData2;
    char *model = (char *)*recvData3;
    void **inputs = (void **)*recvData4;
    char *correct = (char *)*recvData5;

    printf("Output:%p\n", output);
    printf("Temp:%p\n", temp);
    printf("Model:%p\n", model);
    printf("Inputs:%p\n", inputs);
    printf("Correct:%p\n", correct);

    RunCompiledInference(compiledModel, output, temp, inputs, model, correct);

    iob_regfileif_inverted_csrs_set_done(1);
  }

  uart_finish();

  return 0;
}

#endif // TESTER
