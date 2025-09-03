#!/usr/bin/env python3

import argparse
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess
from typing import Callable


def parse_arguments():
    parser = argparse.ArgumentParser(
        prog="verilog_lint.py",
        description="""Verilog lint script.
        Run this tool to lint verilog over multiple modules.
        Currently supports verilator lint.""",
    )
    parser.add_argument(
        "-d",
        "--dir",
        action="append",
        default=None,
        help="Directory to search for Verilog files. Defaults to current directory.",
    )
    parser.add_argument(
        "-c",
        "--config",
        action="append",
        default=[],
        help="""Path to config files.
        Searches for verilator_config.vlt and [module]_waiver.vlt files.
        """,
    )
    parser.add_argument(
        "--fu-dirs",
        action="append",
        default=[],
        help="""Funtions Unit
        Search directory for function units to lint.
        """,
    )
    parser.add_argument(
        "--fu",
        action="append",
        default=[],
        help="""Funtions Unit
        Lint only specified module(s). Overwrites --fu-dirs if set.
        """,
    )
    parser.add_argument(
        "-o",
        "--output",
        default="verilog_lint.rpt",
        help="Output report file.",
    )
    parser.add_argument(
        "--gen-waiver",
        action="store_true",
        help="Generate [module]_waiver.vlt waiver file based on linter warnings.",
    )
    args = parser.parse_args()
    # post process - use current dir if no dir specified
    if not args.dir:
        args.dir = ["."]
    return args


@dataclass
class VerilogModule:
    """Represent a Verilog module to lint"""

    name: str = ""
    vfile: str = ""
    module_tree: list[str] = field(default_factory=list)
    configs: list[str] = field(default_factory=list)
    result: subprocess.CompletedProcess | None = None


def build_module_tree(code: str, vlog_module: VerilogModule) -> None:
    """Build module tree for a single Verilog module.
    Read the module source code and list the instantiated modules.
    NOTE: supports only named port connection syntax:
        module_name instance_name ( .port1(a), .port2(b) );
        module_name #(.PARAM1(P1), .PARAM2(P2) ) instance_name (.port1(a), .port2(b) );
    Args:
        code: str: Verilog module code as string.
        vlog_module (VerilogModule): Verilog module.
    """
    # capture word starting with letter
    word = r"([a-zA-Z_][a-zA-Z0-9_]*)"
    # pattern: word + word + (
    # example: "iob_adder adder ("
    simple_module_pattern = r"\b" + word + r"\s+[a-zA-Z_][a-zA-Z0-9_]\s*\("
    # pattern: word + #(
    # example: "iob_adder adder ("
    param_module_pattern = r"\b" + word + r"\s*#\("
    matches = re.findall(simple_module_pattern, code)
    matches += re.findall(param_module_pattern, code)
    verilog_keywords = [
        "always",
        "assign",
        "begin",
        "case",
        "default",
        "defparam",
        "else",
        "end",
        "endcase",
        "endgenerate",
        "endtask",
        "for",
        "function",
        "generate",
        "genvar",
        "if",
        "include",
        "initial",
        "inout",
        "input",
        "localparam",
        "module",
        "negedge",
        "output",
        "parameter",
        "posedge",
        "reg",
        "signed",
        "task",
        "time",
        "while",
        "wire",
    ]
    for m in matches:
        # filter out keywords and self reference matches
        if m not in verilog_keywords and m != vlog_module.name:
            vlog_module.module_tree.append(m)


def modules_from_dict(fu_dirs: list[str]) -> list[str]:
    """Get all verilog modules in directories.
    Args:
        dirs (list[str]): List of directories to search for Verilog files.
        fu_dirs (list[str]): List of directories to search for function units.
    Returns:
        list[VerilogModule]: List of Verilog module names.
    """
    fus_to_lint: list[str] = []
    for dir in fu_dirs:
        # search for verilog modules in all *.v files
        v_files = list(Path(dir).glob("*.v"))
        if not v_files:
            continue

        # regex: find all text between 'module' and 'endmodule'
        # re.DOTALL makes '.' match newlines as well
        pattern = r"\bmodule\b(.*?)\bendmodule\b"
        for vfile in v_files:
            modules = []
            with open(vfile, "r") as file:
                content = file.read()
                modules = re.findall(pattern, content, re.DOTALL)
                for m in modules:
                    fus_to_lint.append(m.split()[0])

    return fus_to_lint


def get_verilog_modules(dirs: list[str]) -> list[VerilogModule]:
    """Get all verilog modules in directories.
    Args:
        dirs (list[str]): List of directories to search for Verilog files.
    Returns:
        list[VerilogModule]: List of Verilog module names.
    """
    vlog_modules: list = []
    for dir in dirs:
        # search for verilog modules in all *.v files
        v_files = list(Path(dir).glob("*.v"))
        if not v_files:
            continue

        # regex: find all text between 'module' and 'endmodule'
        # re.DOTALL makes '.' match newlines as well
        pattern = r"\bmodule\b(.*?)\bendmodule\b"
        for vfile in v_files:
            modules = []
            with open(vfile, "r") as file:
                content = file.read()
                modules = re.findall(pattern, content, re.DOTALL)
                for m in modules:
                    code = f"module {m}\nendmodule"
                    vlog_module = VerilogModule(
                        name=m.split()[0],
                        vfile=str(vfile),
                    )
                    build_module_tree(code, vlog_module)
                    vlog_modules.append(vlog_module)

    return vlog_modules


def traverse_module_tree(
    top_module: VerilogModule,
    modules: dict[str, VerilogModule],
    process: Callable[[list[str], VerilogModule], None],
) -> list[str]:
    """Process module tree.
    Follows module tree from top_module and gets all files for submodules recursively.
    Args:
        top_module (VerilogModule): The Verilog module to get files from.
        modules (dict[str, VerilogModule]): List of all Verilog modules.
        process (Callable[[list[str], VerilogModule], None]):
            Function to process each module.
    Returns:
        list[str]: List of Verilog files in the module tree.
    """
    traverse_list: list[str] = []
    traverse: deque = deque()
    traverse.append(top_module.name)
    while traverse:
        # get next module name
        m_name = traverse.popleft()
        if m_name in modules:
            module = modules[m_name]  # get module from name
        else:
            continue  # skip if module not found
        process(traverse_list, module)
        # add submodules to traverse queue
        for submodule in module.module_tree:
            traverse.append(submodule)
    # remove duplicates, keep order of appearance
    return list(dict.fromkeys(traverse_list))


def files_from_tree(
    top_module: VerilogModule, modules: dict[str, VerilogModule]
) -> list[str]:
    """Get all files from module tree.
    Follows module tree from top_module and gets all files for submodules recursively.
    Args:
        top_module (VerilogModule): The Verilog module to get files from.
        modules (dict[str, VerilogModule]): List of all Verilog modules.
    Returns:
        list[str]: List of Verilog files in the module tree.
    """

    def append_vfile(t_list: list[str], m: VerilogModule):
        t_list.append(m.vfile)

    return traverse_module_tree(top_module, modules, append_vfile)


def configs_from_tree(
    top_module: VerilogModule, modules: dict[str, VerilogModule]
) -> list[str]:
    """Get all configs from module tree.
    Follows module tree from top_module and gets all configs for submodules recursively.
    Args:
        top_module (VerilogModule): The Verilog module to get files from.
        modules (dict[str, VerilogModule]): List of all Verilog modules.
    Returns:
        list[str]: List of Verilog config files in the module tree.
    """

    def append_configs(t_list: list[str], m: VerilogModule):
        t_list += m.configs

    return traverse_module_tree(top_module, modules, append_configs)


def set_verilator_configs(
    vlog_modules: list[VerilogModule], cfg_dirs: list[str]
) -> None:
    """Set verilator configs for each module.
    Update VerilogModules with respective configs.
    Args:
        vlog_modules (list[VerilogModule]): List of Verilog modules.
        cfg_dirs (list[str]): List of directories to search for config files.
    """
    for module in vlog_modules:
        for cfg_dir in cfg_dirs:
            # Search for verilator_config.vlt
            module.configs += [
                str(c) for c in list(Path(cfg_dir).glob("verilator_config.vlt"))
            ]
            # Search for [module]_waiver.vlt configurations
            module.configs += [
                str(c) for c in list(Path(cfg_dir).glob(f"{module.name}_waiver.vlt"))
            ]


def lint_modules(
    vlog_modules: list[VerilogModule],
    dirs: list[str],
    gen_waiver: bool,
    fus: list[str],
    fu_dirs: list[str],
) -> None:
    """Lint each Verilog module using verilator.
    Update VerilogModule with lint results.
    Args:
        vlog_modules (list[VerilogModule]): List of Verilog modules to lint.
        dirs (list[str]): List of directories to search for Verilog files.
        gen_waiver (bool): Generate waiver file for each module.
        fus (list[str]): List of function units (modules) to lint.
            If empty, lint all modules.
        fu_dirs (list[str]): List of directories to search for function units.
    """
    mod_dict: dict[str, VerilogModule] = {}
    for m in vlog_modules:
        mod_dict[m.name] = m  # convert module list to dict
    include_flags = []

    fus_to_lint: list[str] | None = None
    if fus:
        fus_to_lint = fus
    elif fu_dirs:
        fus_to_lint = modules_from_dict(fu_dirs)

    for dir in dirs:
        include_flags.append(f"-I{dir}")
    for module in vlog_modules:
        if fus_to_lint and module.name not in fus_to_lint:
            # skip if module not in fu list
            # lint all modules if list is empty
            continue
        # run verilator lint command
        lint_cmd = ["verilator", "--lint-only"]
        # add include dirs
        lint_cmd += include_flags
        if gen_waiver:
            waiver_name = f"{module.name}_waiver.vlt"
            lint_cmd += ["--waiver-output", waiver_name]
        lint_cmd += ["--top-module", module.name]
        # waiver files
        lint_cmd += configs_from_tree(module, mod_dict)
        # add verilog source files
        lint_cmd += files_from_tree(module, mod_dict)
        print(f"Running lint command:\n\t{' '.join(lint_cmd)}\n\n")
        module.result = subprocess.run(
            lint_cmd,
            capture_output=True,
            text=True,
        )


def process_results(vlog_modules: list[VerilogModule], output: str) -> None:
    """Process lint results and write to output file.
    Args:
        vlog_modules (list[VerilogModule]): List of Verilog modules with lint results.
        output (str): Output report file path.
    """
    with open(output, "w") as f:
        passed = 0
        failed = 0
        total = 0
        linted_fus = ""
        detailed_warnings = ""
        for module in vlog_modules:
            if not module.result:
                continue  # skip modules that were not linted
            if module.result.returncode == 0:
                passed += 1
                linted_fus += f"[{len(module.module_tree)+1}]{module.name} - PASSED\n"
            else:
                failed += 1
                linted_fus += f"[{len(module.module_tree)+1}]{module.name} - FAILED\n"
                detailed_warnings += f"Module: {module.name}\n"
                detailed_warnings += f"Lint command: {module.result.args}\n"
                detailed_warnings += f"Warnings:\n{module.result.stderr}\n"
                detailed_warnings += "\n=================================\n\n"
            total += 1
        f.write("// Report Generated by verilog_linter.py\n\n")
        f.write("====================\n")
        f.write("Lint Results Summary\n")
        f.write("====================\n")
        f.write(f"Modules lint passed: {passed}\n")
        f.write(f"Modules lint failed: {failed}\n")
        f.write(f"Total Modules linted: {total}\n\n")

        f.write("===================\n")
        f.write("Linted Modules List\n")
        f.write("===================\n")
        f.write(linted_fus)

        f.write("\n======================\n")
        f.write("Detailed Lint Warnings\n")
        f.write("======================\n")
        f.write(detailed_warnings)


if __name__ == "__main__":
    print("=====================")
    print("Verilog Linter Script")
    print("=====================\n")
    args = parse_arguments()
    print(args)

    # 1. Get all modules in dirs
    vlog_modules = get_verilog_modules(args.dir)
    # 2. Set verilator configs for each module
    set_verilator_configs(vlog_modules, args.config)
    # 3. Run verilator lint on each module
    lint_modules(vlog_modules, args.dir, args.gen_waiver, args.fu, args.fu_dirs)
    # 4. Process results into report file
    process_results(vlog_modules, args.output)
