import os
import sys
import shutil
import subprocess as sp
import codecs
import pprint


def RunVersat(versat_spec, versat_top, versat_extra, build_dir, axi_data_w, debug_path):
    versat_args = [
        "versat",
        os.path.realpath(versat_spec),
        "-s",
        f"-b{axi_data_w}",
        "-d",  # DMA
        "-E",  # Extra stuff that is mostly hardcoded for this project
        "-p",
        "iob_csrs_",
        "-t",
        versat_top,
        "-u",
        os.path.realpath("./hardware/units"),
        "-o",
        os.path.realpath(build_dir + "/hardware/src"),  # Output hardware files
        "-O",
        os.path.realpath(build_dir + "/software"),  # Output software files
    ]

    if debug_path:
        versat_args = versat_args + ["-g", debug_path]

    if versat_extra:
        versat_args = versat_args + ["-u", versat_extra]

    print(*versat_args, "\n", file=sys.stderr)
    result = None
    try:
        result = sp.run(versat_args, capture_output=True)
        print("ran versat")
    except Exception as e:
        print(e)
        return []

    returnCode = result.returncode
    decoder = codecs.getdecoder("unicode_escape")
    output = decoder(result.stdout)[0]
    errorOutput = decoder(result.stderr)[0]

    print(output, file=sys.stderr)
    print(errorOutput, file=sys.stderr)
    print(returnCode)

    if returnCode != 0:
        print("Failed to generate accelerator\n", file=sys.stderr)
        exit(returnCode)

    lines = output.split("\n")

    return lines


output = RunVersat("versatSpec.txt", "Test", None, "submodules/iob_versat", 32, None)

shutil.move(
    "submodules/iob_versat/software/versat_emul.c",
    "submodules/iob_versat/software/src/versat_emul.c",
)
shutil.move(
    "submodules/iob_versat/software/iob-versat.c",
    "submodules/iob_versat/software/src/iob_versat.c",
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
                "name": "interface",
                "descr": "",
                "signals": [
                    {"name": "interface_raddr_o", "width": 1},
                    {"name": "interface_i", "width": 1},
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
                        "name": "interface",
                        "type": "R",
                        "n_bits": 32,
                        "rst_val": 0,
                        "log2n_items": 10,
                        "descr": "Versat interface",
                    }
                ],
                "connect": {
                    "clk_en_rst_s": "clk_en_rst_s",
                    "interface_io": "interface",
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
