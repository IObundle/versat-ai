# SPDX-FileCopyrightText: 2025 IObundle
#
# SPDX-License-Identifier: MIT

CORE := versat_ai

SIMULATOR ?= verilator
SYNTHESIZER ?= yosys
LINTER ?= spyglass
BOARD ?= iob_cyclonev_gt_dk

TEST := test1 # Possible values: test1,test2

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

# TODO: When adding more tests, we need a better way of doing this.
test1: $(VERSAT_ACCEL) $(GENERATED_TEST)
	bash -c "source $(PYTHON_ENV)/bin/activate; python3 ./scripts/onnxMain.py tests/generated/ model.onnx software/ software/src"
	cp software/*.bin hardware/simulation
	nix-shell --run "py2hwsw $(CORE) setup --no_verilog_lint --py_params 'use_intmem=$(USE_INTMEM):use_extmem=$(USE_EXTMEM):init_mem=$(INIT_MEM)' $(EXTRA_ARGS);"
	cp -r submodules/iob_versat/software ../versat_ai_V0.8/ # Since python file was not being copied and we need a python script from inside software

test2: $(VERSAT_ACCEL) $(DOWNLOADED_TEST)
	bash -c "source $(PYTHON_ENV)/bin/activate; python3 ./scripts/onnxMain.py tests/mnist_v7/ model.onnx software/ software/src"
	cp software/*.bin hardware/simulation
	nix-shell --run "py2hwsw $(CORE) setup --no_verilog_lint --py_params 'use_intmem=$(USE_INTMEM):use_extmem=$(USE_EXTMEM):init_mem=$(INIT_MEM)' $(EXTRA_ARGS);"
	cp -r submodules/iob_versat/software ../versat_ai_V0.8/ # Since python file was not being copied and we need a python script from inside software

pc-emul-run: $(TEST)
	nix-shell --run "make -C ../$(CORE)_V$(VERSION)/ pc-emul-run"

sim-run: $(TEST)
	nix-shell --run "make -C ../$(CORE)_V$(VERSION)/ sim-run SIMULATOR=$(SIMULATOR)"

# Need to be inside nix-shell for fast- rules to work. Mostly used to speed up development instead of waiting for setup everytime
fast-versat:
	python3 ./scripts/versatGenerate.py

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

# Rules to force certain files to be build, mostly for debugging as the files should just be built by the rules of the makefile
test-generate: 
	rm -f $(GENERATED_TEST)
	$(MAKE) $(GENERATED_TEST) 
	bash -c "source $(PYTHON_ENV)/bin/activate; python3 ./scripts/onnxMain.py tests/generated/ model.onnx software/ software/src"

versat-generate:
	rm -f $(VERSAT_ACCEL)
	$(MAKE) $(VERSAT_ACCEL)

clean:
	nix-shell --run "py2hwsw $(CORE) clean --build_dir '$(BUILD_DIR)'"
	@rm -rf ./tests
	@rm -rf ./submodules/iob_versat
	@rm -rf ./hardware/simulation/*.bin
	@rm -rf ./software/*.bin
	@rm -f  ./software/src/code.c ./software/src/modelInfo.h
	@rm -rf ../*.summary ../*.rpt
	@find . -name \*~ -delete

full-clean: clean
	@rm -rf $(PYTHON_ENV)

# Remove all __pycache__ folders with python bytecode
python-cache-clean:
	find . -name "*__pycache__" -exec rm -rf {} \; -prune

# VLINT_FLAGS += -d ./hardware/src
VLINT_FLAGS += -d ./submodules/VERSAT/hardware/src
# VLINT_FLAGS += -d ./submodules/VERSAT/hardware/src/units
VLINT_FLAGS += -c ./hardware/lint
VLINT_FLAGS += -o lint.rpt
VLINT_FLAGS += --gen-waiver
lint-all-fus:
	nix-shell --run "./scripts/verilog_linter.py $(VLINT_FLAGS)"
	cat lint.rpt

.PHONY: setup full-clean clean python-cache-clean
