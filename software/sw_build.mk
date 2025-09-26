# SPDX-FileCopyrightText: 2025 IObundle
#
# SPDX-License-Identifier: MIT

#########################################
#            Embedded targets           #
#########################################
ROOT_DIR ?=..

include $(ROOT_DIR)/software/auto_sw_build.mk

# Local embedded makefile settings for custom bootloader and firmware targets.

#Function to obtain parameter named $(1) in verilog header file located in $(2)
#Usage: $(call GET_MACRO,<param_name>,<vh_path>)
GET_MACRO = $(shell grep "define $(1)" $(2) | rev | cut -d" " -f1 | rev)

#Function to obtain parameter named $(1) from versat_ai_conf.vh
GET_VERSAT_AI_CONF_MACRO = $(call GET_MACRO,VERSAT_AI_$(1),$(ROOT_DIR)/hardware/src/versat_ai_conf.vh)

versat_ai_bootrom.hex: ../../software/versat_ai_preboot.bin ../../software/versat_ai_boot.bin
	../../scripts/makehex.py $^ 00000080 $(call GET_VERSAT_AI_CONF_MACRO,BOOTROM_ADDR_W) $@

versat_ai_firmware.hex: versat_ai_firmware.bin
	../../scripts/makehex.py $< $(call GET_VERSAT_AI_CONF_MACRO,MEM_ADDR_W) $@
	../../scripts/makehex.py --split $< $(call GET_VERSAT_AI_CONF_MACRO,MEM_ADDR_W) $@

versat_ai_firmware.bin: ../../software/versat_ai_firmware.bin
	cp $< $@

../../software/%.bin:
	make -C ../../ sw-build

UTARGETS+=build_versat_ai_software tb
TB_SRC+=./simulation/src/iob_uart_csrs.c
TB_INCLUDES ?=-I./simulation/src

TEMPLATE_LDS=src/$@.lds

VERSAT_AI_INCLUDES=-Isrc -I.

VERSAT_AI_LFLAGS=-Wl,-L,src,-Bstatic,-T,$(TEMPLATE_LDS),--strip-debug

# FIRMWARE SOURCES
VERSAT_AI_FW_SRC=src/versat_ai_firmware.S
VERSAT_AI_FW_SRC+=src/versat_ai_firmware.c
VERSAT_AI_FW_SRC+=src/iob_printf.c

VERSAT_AI_FW_SRC+=src/code.c
VERSAT_AI_FW_SRC+=src/staticSource.c
VERSAT_AI_FW_SRC+=src/versatSource.c

# PERIPHERAL SOURCES
DRIVERS=$(addprefix src/,$(addsuffix .c,$(PERIPHERALS)))
# Only add driver files if they exist
VERSAT_AI_FW_SRC+=$(foreach file,$(DRIVERS),$(wildcard $(file)*))
VERSAT_AI_FW_SRC+=$(addprefix src/,$(addsuffix _csrs.c,$(PERIPHERALS)))

# BOOTLOADER SOURCES
VERSAT_AI_BOOT_SRC+=src/versat_ai_boot.S
VERSAT_AI_BOOT_SRC+=src/versat_ai_boot.c
VERSAT_AI_BOOT_SRC+=src/iob_uart.c
VERSAT_AI_BOOT_SRC+=src/iob_uart_csrs.c

# PREBOOT SOURCES
VERSAT_AI_PREBOOT_SRC=src/versat_ai_preboot.S

build_versat_ai_software: versat_ai_firmware versat_ai_boot versat_ai_preboot

ifneq ($(USE_FPGA),)
WRAPPER_CONFS_PREFIX=versat_ai_$(BOARD)
WRAPPER_DIR=src
else
WRAPPER_CONFS_PREFIX=iob_uut
WRAPPER_DIR=simulation/src
endif

iob_bsp:
	sed 's/$(WRAPPER_CONFS_PREFIX)/IOB_BSP/Ig' $(WRAPPER_DIR)/$(WRAPPER_CONFS_PREFIX)_conf.h > src/iob_bsp.h

versat_ai_firmware: iob_bsp
	make $@.elf INCLUDES="$(VERSAT_AI_INCLUDES)" LFLAGS="$(VERSAT_AI_LFLAGS) -Wl,-Map,$@.map" SRC="$(VERSAT_AI_FW_SRC)" TEMPLATE_LDS="$(TEMPLATE_LDS)"

versat_ai_boot: iob_bsp
	make $@.elf INCLUDES="$(VERSAT_AI_INCLUDES)" LFLAGS="$(VERSAT_AI_LFLAGS) -Wl,-Map,$@.map" SRC="$(VERSAT_AI_BOOT_SRC)" TEMPLATE_LDS="$(TEMPLATE_LDS)"

versat_ai_preboot:
	make $@.elf INCLUDES="$(VERSAT_AI_INCLUDES)" LFLAGS="$(VERSAT_AI_LFLAGS) -Wl,-Map,$@.map" SRC="$(VERSAT_AI_PREBOOT_SRC)" TEMPLATE_LDS="$(TEMPLATE_LDS)" NO_HW_DRIVER=1


.PHONY: build_versat_ai_software iob_bsp versat_ai_firmware versat_ai_boot versat_ai_preboot

#########################################
#         PC emulation targets          #
#########################################
# Local pc-emul makefile settings for custom pc emulation targets.
EMUL_HDR+=iob_bsp

# SOURCES
EMUL_SRC+=src/versat_ai_firmware.c
EMUL_SRC+=src/iob_printf.c

EMUL_SRC+=src/versat_emul.c
EMUL_SRC+=src/code.c
EMUL_SRC+=src/staticSource.c
EMUL_SRC+=src/versatSource.c

# PERIPHERAL SOURCES
EMUL_SRC+=$(addprefix src/,$(addsuffix .c,$(PERIPHERALS)))


EMUL_SRC+=$(addprefix src/,$(addsuffix _csrs_pc_emul.c,$(PERIPHERALS)))

EMUL_SRC:=$(filter-out src/iob_versat.c,$(EMUL_SRC))

# include software build segment of child systems
# child systems can add their own child_sw_build.mk without having to override this one.
ifneq ($(wildcard $(ROOT_DIR)/software/child_sw_build.mk),)
include $(ROOT_DIR)/software/child_sw_build.mk
endif
