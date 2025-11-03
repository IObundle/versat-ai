# SPDX-FileCopyrightText: 2025 IObundle
#
# SPDX-License-Identifier: MIT

CORE := versat_ai

SIMULATOR ?= verilator
SYNTHESIZER ?= yosys
LINTER ?= spyglass
BOARD ?= iob_cyclonev_gt_dk

TEST := Generated # Run setupTest.py to see the possible values for this

PYTHON_ENV := ../python_env
VERSAT_ACCEL := ./submodules/iob_versat/iob_versat.py
VERSAT_SUBMODULE := ./submodules/VERSAT
GENERATED_TEST := ./tests/generated/model.onnx
DOWNLOADED_TEST := ./tests/mnist_v7/model.onnx
ALL_SCRIPTS := $(wildcard ./scripts/*.py)

BUILD_DIR ?= $(shell nix-shell --run "py2hwsw $(CORE) print_build_dir")

USE_INTMEM ?= 0
USE_EXTMEM ?= 1
INIT_MEM ?= 1

VERSION ?=$(shell cat versat_ai.py | grep version | cut -d '"' -f 4)

ifneq ($(DEBUG),)
EXTRA_ARGS +=--debug_level $(DEBUG)
endif

# Resources that are generated as they are needed. Mostly the generated tests and Versat
$(VERSAT_ACCEL): versatSpec.txt
	@rm -f $(VERSAT_SUBMODULE)/iob_versat.py
	nix-shell --run "python3 ./scripts/versatGenerate.py"

$(PYTHON_ENV):
	./scripts/makePythonEnv.sh

$(GENERATED_TEST): $(PYTHON_ENV) $(ALL_SCRIPTS)
	bash -c "source $(PYTHON_ENV)/bin/activate ; python3 ./scripts/generateSimpleTests.py ./tests/generated/"

$(DOWNLOADED_TEST): $(PYTHON_ENV)
	./scripts/downloadTests.sh

pc-emul-run: $(VERSAT_ACCEL)
	python3 ./setupTest.py $(TEST)
	nix-shell --run "make -C ../$(CORE)_V$(VERSION)/ pc-emul-run"

sim-run: $(VERSAT_ACCEL)
	python3 ./setupTest.py $(TEST)
	nix-shell --run "make -C ../$(CORE)_V$(VERSION)/ sim-run SIMULATOR=$(SIMULATOR)"

# Need to be inside nix-shell for fast rules to work. Mostly used to speed up development instead of waiting for setup everytime
fast-versat:
	python3 ./scripts/versatGenerate.py

fast-pc-no-generate:
	cp -r software ../versat_ai_V0.8/
	cp -r submodules/iob_versat/software ../versat_ai_V0.8/
	make -C ../versat_ai_V0.8/ pc-emul-run

fast-pc-soft: fast-versat
	cp -r software ../versat_ai_V0.8/
	cp -r submodules/iob_versat/software ../versat_ai_V0.8/
	make -C ../versat_ai_V0.8/ pc-emul-run

fast-pc-hard: fast-versat
	cp -r software ../versat_ai_V0.8/
	cp -r hardware ../versat_ai_V0.8/
	cp -r submodules/iob_versat/software ../versat_ai_V0.8/
	cp -r submodules/iob_versat/hardware ../versat_ai_V0.8/
	make -C ../versat_ai_V0.8/ pc-emul-run

fast-sim-run:
	cp -r software ../versat_ai_V0.8/
	cp -r hardware ../versat_ai_V0.8/
	cp -r submodules/iob_versat/hardware ../versat_ai_V0.8/
	cp -r submodules/iob_versat/software ../versat_ai_V0.8/
	make -C ../versat_ai_V0.8/ sim-run SIMULATOR=$(SIMULATOR) VCD=$(VCD)

# Rules to force certain files to be build, mostly for debugging and to support the runTest.py script
# Do not call them directly unless you know what you are doing
do-test:
	bash -c "source $(PYTHON_ENV)/bin/activate; python3 ./scripts/onnxMain.py $(TEST_PATH) model.onnx software/ software/src"

test-generate: 
	rm -f $(GENERATED_TEST)
	$(MAKE) $(GENERATED_TEST) 
	bash -c "source $(PYTHON_ENV)/bin/activate; python3 ./scripts/onnxMain.py tests/generated/ model.onnx software/ software/src"

test-setup:
	mkdir -p hardware/simulation
	cp software/*.bin hardware/simulation
	nix-shell --run "py2hwsw $(CORE) setup --no_verilog_lint --py_params 'use_intmem=$(USE_INTMEM):use_extmem=$(USE_EXTMEM):init_mem=$(INIT_MEM)' $(EXTRA_ARGS);"
	cp -r submodules/iob_versat/software ../versat_ai_V0.8/ # Since python file was not being copied and we need a python script from inside software

versat-generate:
	rm -f $(VERSAT_ACCEL)
	$(MAKE) $(VERSAT_ACCEL)

clean:
	nix-shell --run "py2hwsw $(CORE) clean --build_dir '$(BUILD_DIR)'"
	@rm -rf ./submodules/iob_versat
	@rm -rf ./hardware/simulation/*.bin
	@rm -rf ./software/*.bin
	@rm -f  ./software/src/code.c ./software/src/modelInfo.h ./software/src/testInfo.h 
	@rm -rf ../*.summary ../*.rpt
	@rm -rf ./*.rpt
	@find . -name \*~ -delete

full-clean: clean
	@rm -rf ./tests
	@rm -rf $(PYTHON_ENV)

# Remove all __pycache__ folders with python bytecode
python-cache-clean:
	find . -name "*__pycache__" -exec rm -rf {} \; -prune

# Use --fu-dir to list all FUs for linting
VLINT_FLAGS += --fu-dir ./hardware/src
VLINT_FLAGS += --fu-dir ./hardware/units
VLINT_FLAGS += --fu-dir ./submodules/VERSAT/hardware/src/units
# Use build directory to find all verilog sources and headers
VLINT_FLAGS += -d ../versat_ai_V0.8/hardware/src
VLINT_FLAGS += -c ./hardware/lint
VLINT_FLAGS += -c ./submodules/VERSAT/hardware/lint
VLINT_FLAGS += -o lint.rpt
lint-all-fus: clean $(VERSAT_ACCEL)
	python3 ./setupTest.py Generated
	nix-shell --run "./scripts/verilog_linter.py $(VLINT_FLAGS)"
	cat lint.rpt

FU?=iob_fp_clz
lint-fu: clean $(VERSAT_ACCEL)
	python3 ./setupTest.py Generated
	nix-shell --run "./scripts/verilog_linter.py $(VLINT_FLAGS) --fu $(FU)"
	cat lint.rpt

coverage-all-fus: clean $(VERSAT_ACCEL)
	python3 ./setupTest.py Generated
	nix-shell --run "make -C ../versat_ai_V0.8/hardware/simulation/coverage all"

.PHONY: setup full-clean clean python-cache-clean
