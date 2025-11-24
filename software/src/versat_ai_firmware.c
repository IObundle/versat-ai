/*
 * SPDX-FileCopyrightText: 2025 IObundle
 *
 * SPDX-License-Identifier: MIT
 */

#include "iob_bsp.h"
#include "iob_printf.h"
#include "iob_timer.h"
#include "iob_uart.h"
#include "versat_accel.h"
#include "versat_ai_conf.h"
#include "versat_ai_mmap.h"
#include <string.h>

#ifndef PC
#include "iob_eth.h"
#endif

#include "versat_ai.h"

// Contains info for each test.
#include "testInfo.h"

#ifndef ARRAY_SIZE
#define ARRAY_SIZE(ARR) ((sizeof(ARR) / sizeof(ARR[0])))
#endif

#ifndef OFFSET_PTR
#define OFFSET_PTR(PTR, OFFSET) ((void *)(((char *)PTR) + OFFSET))
#endif

#ifdef PC
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

#ifndef PC
uint32_t uart_request_ethernet_recvfile(const char *file_name) {
  uart_puts(UART_PROGNAME);
  uart_puts(": requesting to receive file by ethernet\n");

  // send file receive by ethernet request
  uart_putc(0x13);

  // send file name (including end of string)
  uart_puts(file_name);
  uart_putc(0);

  // receive file size
  uint32_t file_size = uart_getc();
  file_size |= ((uint32_t)uart_getc()) << 8;
  file_size |= ((uint32_t)uart_getc()) << 16;
  file_size |= ((uint32_t)uart_getc()) << 24;

  // send ACK before receiving file
  uart_putc(ACK);

  return file_size;
}

void ethernet_receive_file(const char *path, void *buffer, int expectedSize) {
  if (expectedSize == 0) {
    return;
  }
  uint32_t size = uart_request_ethernet_recvfile(path);
  eth_rcv_file(buffer, size);
}
#endif

void FastReceiveFile(const char *pathPrefix, const char *path, void *buffer,
                     int expectedSize) {
  char fullPath[128];
  snprintf(fullPath, 128, "%s_%s", pathPrefix, path);

#ifdef PC
  FILE *f = fopen(fullPath, "r");
  if (!f) {
    printf("Problem opening file for reading: %s\n", fullPath);
    return;
  }

  long int size = GetFileSize(f);
  fread(buffer, sizeof(char), size, f);
  fclose(f);
#else
  ethernet_receive_file(fullPath, buffer, expectedSize);
#endif
}

void silent_clear_cache() {
#ifndef PC
  for (unsigned int i = 0; i < 10; i++)
    asm volatile("nop");
  // Flush VexRiscv CPU internal cache
  asm volatile(".word 0x500F" ::: "memory");
#endif
}

void silent_clear_cache_args(void *ptr, size_t size) { silent_clear_cache(); }

void clear_cache() {
#ifndef PC
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

#ifndef PC
  uart_puts("\nGonna init ethernet\n");
  eth_init(ETH0_BASE, &silent_clear_cache);
  eth_wait_phy_rst();
#endif

  uart_puts("\nGonna init versat!\n");
  SetVersatDebugPrintfFunction(printf);
  versat_init(VERSAT0_BASE);

#ifdef DEBUG
  PrintU64InHex(1ull << 0);
  PrintU64InHex(1ull << 8);
  PrintU64InHex(1ull << 16);
  PrintU64InHex(1ull << 24);
  PrintU64InHex(1ull << 32);
  PrintU64InHex(1ull << 40);
  PrintU64InHex(1ull << 48);
  PrintU64InHex(1ull << 56);
  PrintU64InHex(1ull << 63);
#endif

  ConfigCreateVCD(false);

  Versat_SetTimeMeasurementFunction(timer_get_count);
  Versat_SetPrintFunction(printf);
  Versat_SetClearCache(silent_clear_cache_args);

  printf("Versat base: %x\n", VERSAT0_BASE);

#ifdef DEBUG
  int stackVar;
  printf("Stack  : %p\n", &stackVar);
#endif

  // We allocate a little bit more just in case.
  // Also need to allocate a bit more to ensure that Align4 works fine.
  int extra = 16;

  for (int i = 0; i < ARRAY_SIZE(testModels); i++) {
    TestModelInfo info = *testModels[i];

    printf("\n==============================\n");
    printf("Gonna run the full test named: %s", info.nameSpace);
    printf("\n==============================\n\n\n");

    void *output = Align4(malloc(info.outputSize + extra));
    void *temp = Align4(malloc(info.tempSize + extra));
    void *model = Align4(malloc(info.modelSize + extra));
    void *correct = Align4(malloc(info.correctSize + extra));
    void *inputMemory = Align4(malloc(info.totalInputSize + extra));

    void **inputs = Align4(malloc(sizeof(void *) * info.inputCount));
    for (int i = 0; i < info.inputCount; i++) {
      inputs[i] = OFFSET_PTR(inputMemory, info.inputOffsets[i]);
    }

    void *total;
    if (info.inputCount == 0) {
      total = OFFSET_PTR(correct, info.correctSize);
    } else {
      total = inputs[info.inputCount - 1];
    }

#ifdef DEBUG
    printf("Output : %p\n", output);
    printf("Temp   : %p\n", temp);
    printf("Model  : %p\n", model);
    printf("Correct: %p\n", correct);
    printf("Input  : %p\n", inputMemory);
    printf("Total  : %p\n", total);

    if (((void *)total) > ((void *)&stackVar)) {
      printf(
          "Error, we run out of memory, increase the value of firm_w argument "
          "and setup again\n");
      uart_finish();
      return 0;
    }
#endif

    FastReceiveFile(info.nameSpace, "correctOutputs.bin", correct,
                    info.correctSize);
    FastReceiveFile(info.nameSpace, "model.bin", model, info.modelSize);
    FastReceiveFile(info.nameSpace, "inputs.bin", inputMemory,
                    info.totalInputSize);

    uint64_t start = timer_get_count();
    info.softwareInferenceFunction(output, temp, inputs, model);
    uint64_t end = timer_get_count();

    PrintTimeElapsed("\nTest individual time", start, end);

    free(output);
    free(temp);
    free(model);
    free(correct);
    free(inputMemory);
  }

#ifdef PC
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
