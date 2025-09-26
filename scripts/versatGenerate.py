import os
import sys
import shutil
import subprocess as sp
import codecs
import pprint
import time


def RunVersat(versat_spec, versat_top, versat_extra, build_dir, axi_data_w, debug_path):
    versat_args = [
        "versat",
        os.path.realpath(versat_spec),
        "-s",
        f"-b{axi_data_w}",
        "-d",  # DMA
        "-p",
        "iob_csrs_",
        "-t",
        versat_top,
        "-u",
        os.path.realpath("./hardware/units"),
        "-o",
        os.path.realpath(
            os.path.join(build_dir, "hardware", "src")
        ),  # Output hardware files
        "-O",
        os.path.realpath(os.path.join(build_dir, "software")),
        "-g",
        os.path.realpath("../debug"),  # Output software files
    ]

    if debug_path:
        versat_args = versat_args + ["-g", debug_path]

    if versat_extra:
        versat_args = versat_args + ["-u", versat_extra]

    print(*versat_args, "\n", file=sys.stderr)
    result = sp.run(versat_args, capture_output=True, encoding="utf-8")

    returnCode = result.returncode
    output = result.stdout
    errorOutput = result.stderr

    print(output, file=sys.stderr)
    print(errorOutput, file=sys.stderr)

    if returnCode != 0:
        print(f"Failed to generate accelerator {returnCode}\n", file=sys.stderr)
        exit(returnCode)

    lines = output.split("\n")

    return lines


if __name__ == "__main__":
    try:
        output = RunVersat(
            "./versatSpec.txt", "Test", None, "./submodules/iob_versat", 32, None
        )
    except Exception as e:
        print("Failed to generate Versat:")
        print(e)
        sys.exit(-1)

    try:
        os.mkdir("./submodules/iob_versat/software/src/")
    except:
        pass  # Nothing if dir already exists

    shutil.move(
        "./submodules/iob_versat/software/versat_emul.c",
        "./submodules/iob_versat/software/src/versat_emul.c",
    )
    shutil.move(
        "./submodules/iob_versat/software/iob-versat.c",
        "./submodules/iob_versat/software/src/iob_versat.c",
    )

    with open("submodules/iob_versat/iob_versat.py", "w") as f:
        attributes_dict = {
            "generate_hw": True,
            "confs": [
                {
                    "name": "DATA_W",
                    "type": "P",
                    "val": "32",
                    "min": "NA",
                    "max": "NA",
                    "descr": "Data bus width",
                },
                {
                    "name": "WDATA_W",
                    "type": "P",
                    "val": "1",
                    "min": "NA",
                    "max": "8",
                    "descr": "",
                },
            ],
            "ports": [
                {
                    "name": "clk_en_rst_s",
                    "signals": {"type": "iob_clk"},
                    "descr": "Clock, clock enable and reset",
                },
                {
                    "name": "axi_out_m",
                    "signals": {
                        "type": "axi",
                        "ID_W": "AXI_ID_W",
                        "ADDR_W": "AXI_ADDR_W",
                        "DATA_W": "AXI_DATA_W",
                        "LEN_W": "AXI_LEN_W",
                        "LOCK_W": 1,
                    },
                    "descr": "AXI wires",
                },
            ],
            "wires": [
                {
                    "name": "csr_interface",
                    "descr": "",
                    "signals": [
                        {"name": "interface_w_en_i", "width": 1},
                        {"name": "interface_w_strb_i", "width": 1},
                        {"name": "interface_w_addr_i", "width": 1},
                        {"name": "interface_w_data_i", "width": 1},
                        {"name": "interface_w_ready_o", "width": 1},
                    ],
                }
            ],
            "subblocks": [
                {
                    "core_name": "iob_csrs",
                    "instance_name": "iob_csrs",
                    "instance_description": "Control/Status Registers",
                    "csr_if": "iob",
                    "csrs": [
                        {
                            "name": "csr_interface",
                            "mode": "R",
                            "n_bits": 32,
                            "rst_val": 0,
                            "log2n_items": 10,
                            "descr": "Versat interface",
                        }
                    ],
                    "connect": {
                        "clk_en_rst_s": "clk_en_rst_s",
                        "csr_interface_write_io": "interface",
                    },
                }
            ],
        }

        f.write(
            f"""
def setup(py_params_dict):
    attributes_dict = {attributes_dict.__repr__()}

    return attributes_dict"""
        )
