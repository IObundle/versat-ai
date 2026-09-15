#include <stdio.h>

#include "src/versat_ai_conf.h"

#define MIN(A, B) ((A) < (B) ? (A) : (B))

long int GetFileSize(FILE *file) {
  long int mark = ftell(file);

  fseek(file, 0, SEEK_END);
  long int size = ftell(file);

  fseek(file, mark, SEEK_SET);

  return size;
}

static int CharToInt(char ch) {
  if (ch >= '0' && ch <= '9') {
    return ch - '0';
  } else if (ch >= 'A' && ch <= 'F') {
    return 10 + (ch - 'A');
  } else if (ch >= 'a' && ch <= 'f') {
    return 10 + (ch - 'a');
  }
  return 0;
}

int ParseInt(char *str) {
  int res = 0;
  for (int i = 0;; i++) {
    if (str[i] == '\0') {
      break;
    }

    res *= 10;
    res += CharToInt(str[i]);
  }

  return res;
}

#define MAX_HEX_FILES 8

int main(int argc, char *argv[]) {
  char *binfile = argv[1];
  char *memsize = argv[2];
  char *outputFile = argv[3];

  int memSize = ParseInt(memsize);

  printf("In:%s\nMem:%d\nOut:%s\n", binfile, memSize, outputFile);

  FILE *in = fopen(binfile, "rb");

  char pathBuffer[1024];

  int size = sprintf(pathBuffer, "%s", binfile);
  pathBuffer[size - 4] = '_';
  pathBuffer[size - 3] = '0';
  pathBuffer[size - 2] = '.';
  pathBuffer[size - 1] = 'h';
  pathBuffer[size] = 'e';
  pathBuffer[size + 1] = 'x';

  printf("%s\n", pathBuffer);

  int hexfiles = (VERSAT_AI_AXI_DATA_W / 8);
  FILE *filesArray[MAX_HEX_FILES];

  for (int i = 0; i < hexfiles; i++) {
    pathBuffer[size - 3] = '0' + i;
    filesArray[i] = fopen(pathBuffer, "w");
  }

  FILE *out = fopen(outputFile, "w");
  long int inSize = GetFileSize(in);

  unsigned char buffer[1024 * MAX_HEX_FILES];

  int amountRead = 0;
  for (int i = 0; i < inSize; i += amountRead) {
    int leftover = MIN(inSize - i, 1024);

    amountRead = fread(buffer, sizeof(unsigned char), leftover, in);

    if (amountRead < 0) {
      printf("ERROR reading\n");
      break;
    }
    if (amountRead == 0) {
      printf("ERROR, no more to read\n");
      break;
    }

    for (int j = 0; j < amountRead; j += hexfiles) {
      for (int k = hexfiles - 1; k >= 0; k--) {
        fprintf(out, "%02x", buffer[j + k]);
      }

      for (int k = 0; k < hexfiles; k++) {
        fprintf(filesArray[k], "%02x\n", buffer[j + k]);
      }

      fprintf(out, "\n");
    }
  }

  fclose(in);
  fclose(out);

  for (int i = 0; i < hexfiles; i++) {
    fclose(filesArray[i]);
  }

  return 0;
}
