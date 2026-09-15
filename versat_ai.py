# SPDX-FileCopyrightText: 2025 IObundle
#
# SPDX-License-Identifier: MIT


def setup(py_params: dict):
    mem_addr_w = 30
    system_w = mem_addr_w
    name = "versat_ai"
    addr_w = 32

    axi_data_w = int(py_params.get("axi_data_w", "32"))
    dataAdapter = "axi_adapter_direct"
    if axi_data_w != 32:
        dataAdapter = "axi_adapter_wider"

    # Set new default values for python parameters of iob_system (parent module)
    # List of iob_system python parameters available at: https://github.com/IObundle/py2hwsw/blob/main/py2hwsw/lib/iob_system/iob_system.py
    iob_system_default_overrides = {
        "init_mem": False,
        "use_intmem": False,
        "use_extmem": True,
        "use_ethernet": False,
        "mem_addr_w": mem_addr_w,
        "cpu": "iob_vexriscv",
        "fw_addr_w": 24,
        "bootrom_addr_w": 12,
        # Tester configuration
        "include_tester": False,
        "tester_use_ethernet": True,
    }

    py_params = update_params(iob_system_default_overrides, py_params)

    # NOTE: Two configurations for this SUT core:
    # 1) SUT only (versat-ai without tester):
    #  - SUT uses ethernet
    #  - SUT does not have (external) memory initialized
    # 2) SUT+Tester (versat-ai and tester):
    #  - SUT does not use ethernet
    #  - SUT assumes external memory is initialized (tester handles initialization)

    if py_params["include_tester"]:
        py_params["use_ethernet"] = False  # No ethernet between SUT and Tester
        py_params["init_mem"] = True  # Tester initializes memory

    # setup custom xbar to include more subordinates (versat core)
    xbar_subblock = {
        "core_name": "iob_axi_full_xbar",
        "name": f"{name}_axi_full_xbar",
        "instance_name": "iob_axi_full_xbar",
        "instance_description": "AXI full xbar instance",
        "parameters": {
            "ID_W": "AXI_ID_W",
            "LEN_W": "AXI_LEN_W",
        },
        "connect": {
            "clk_en_rst_s": "clk_en_rst_s",
            "rst_i": "rst",
            "s0_axi_s": "delayed_cpu_d",
            "s1_axi_s": "delayed_cpu_i",
            # Manager interfaces connected below
        },
        "addr_w": addr_w,
        "data_w": 32,
        "lock_w": 1,
        "num_subordinates": 2,
    }
    # Add ethernet connections in xbar subblock if needed
    if py_params["use_ethernet"]:
        subordinate_if_number = xbar_subblock["num_subordinates"]
        xbar_subblock["num_subordinates"] += 1
        xbar_subblock["connect"] |= {
            f"s{subordinate_if_number}_axi_s": (
                "eth_axi",
                ["eth_axi_awlock[0]", "eth_axi_arlock[0]"],
            )
        }
    xbar_manager_interfaces = {
        "use_extmem": "narrow_axi",
        "use_bootrom": (
            "bootrom_cbus",
            [
                "{unused_m2_araddr_bits, bootrom_axi_araddr}",
                "{unused_m2_awaddr_bits, bootrom_axi_awaddr}",
            ],
        ),
        "use_peripherals": (
            "axi_periphs_cbus",
            [
                "{unused_m3_araddr_bits, periphs_axi_araddr}",
                "{unused_m3_awaddr_bits, periphs_axi_awaddr}",
                "periphs_axi_awlock[0]",
                "periphs_axi_arlock[0]",
            ],
        ),
    }
    xbar_sel_w = (3 - 1).bit_length()

    # Connect xbar manager interfaces
    num_managers = 0
    for interface_connection in xbar_manager_interfaces.values():
        xbar_subblock["connect"] |= {f"m{num_managers}_axi_m": interface_connection}
        num_managers += 1
    xbar_subblock["num_managers"] = num_managers

    subblocks = [
        xbar_subblock,
        {
            "core_name": "iob_axi2iob",
            "instance_name": "periphs_axi2iob",
            "instance_description": "Convert AXI to AXI lite for CLINT",
            "parameters": {
                "AXI_ID_WIDTH": "AXI_ID_W",
                "AXI_LEN_WIDTH": "AXI_LEN_W",
                "ADDR_WIDTH": 32 - xbar_sel_w,
                "DATA_WIDTH": 32,
            },
            "connect": {
                "clk_en_rst_s": "clk_en_rst_s",
                "axi_s": (
                    "axi_periphs_cbus",
                    [
                        "periphs_axi_arlock[0]",
                        "periphs_axi_awlock[0]",
                    ],
                ),
                "iob_m": "iob_periphs_cbus",
            },
        },
        {
            "name": "iob_axi_merge",
            "core_name": "axi_merge",
            "instance_name": "versat_uut_merge",
            # "num_subordinates": 2,
            # "data_w": axi_data_w,
            # "addr_w": 32,
            "parameters": {"DATA_WIDTH": axi_data_w, "ADDR_WIDTH": 32},
            "connect": {
                "axi_s0_s": "proper_axi",
                "axi_s1_s": "versat_axi",
                "axi_m": (
                    "axi_m",
                    [
                        "{unused_wires_0, axi_araddr_o}",
                        "{unused_wires_1, axi_awaddr_o}",
                    ],
                ),
            },
        },
        {
            "core_name": dataAdapter,
            "instance_name": "narrow_to_wide",
            "parameters": {
                "ADDR_WIDTH": addr_w,
                "S_DATA_WIDTH": 32,
                "M_DATA_WIDTH": "AXI_DATA_W",
            },
            "connect": {
                "clk_en_rst_s": "clk_en_rst_s",
                "axi_s": "narrow_axi",
                "axi_m": "proper_axi",
            },
        },
        {
            # Instantiate a UART core from: https://github.com/IObundle/py2hwsw/tree/main/py2hwsw/lib/hardware/iob_uart
            "core_name": "iob_uart",
            "instance_name": "UART0",
            "instance_description": "UART peripheral",
            "is_peripheral": True,
            "parameters": {},
            "connect": {
                "clk_en_rst_s": "clk_en_rst_s",
                # Cbus connected automatically
                "rs232_m": "rs232_m",
            },
        },
        {
            # Instantiate a TIMER core from: https://github.com/IObundle/py2hwsw/tree/main/py2hwsw/lib/hardware/iob_timer
            "core_name": "iob_timer",
            "instance_name": "TIMER0",
            "instance_description": "Timer peripheral",
            "is_peripheral": True,
            "parameters": {},
            "connect": {
                "clk_en_rst_s": "clk_en_rst_s",
                # Cbus connected automatically
            },
        },
        {
            "core_name": "iob_versat",
            "instance_name": "VERSAT0",
            "instance_description": "Versat accelerator",
            "is_peripheral": True,
            "parameters": {"AXI_DATA_W": axi_data_w},
            "connect": {
                "clk_en_rst_s": "clk_en_rst_s",
                "axi_out_m": "versat_axi",
                # Cbus connected automatically
            },
        },
        {
            "core_name": "versat_axi_pipeline",
            "instance_name": "dbus_delay",
            "connect": {
                "clk_en_rst_s": "clk_en_rst_s",
                "axi_s": "cpu_dbus",
                "axi_m": "delayed_cpu_d",
            },
        },
        {
            "core_name": "versat_axi_pipeline",
            "instance_name": "ibus_delay",
            "connect": {
                "clk_en_rst_s": "clk_en_rst_s",
                "axi_s": "cpu_ibus",
                "axi_m": "delayed_cpu_i",
            },
        },
    ]

    if py_params["include_tester"]:
        subblocks += [
            {
                "core_name": "iob_regfileif",
                "instance_name": "REGFILEIF0",
                "instance_description": "Provides Register file interface with registers used to configure, control and monitor the Versat system.",
                "is_peripheral": True,
                "internal_csr_if_widths": {
                    "ADDR_W": 3,
                    "DATA_W": 32,
                },
                "external_csr_if_widths": {
                    "ADDR_W": 3,
                    "DATA_W": 32,
                },
                "csrs": [
                    {
                        "name": "regfileif",
                        "descr": "REGFILEIF software accessible registers.",
                        "regs": [
                            {
                                "name": "start",
                                "descr": "Set 1 to start. versat_ai sets this to 0 to acknowledge start received",
                                "mode": "RW",
                                "n_bits": 1,
                                "rst_val": 0,
                                "log2n_items": 0,
                            },
                            {
                                "name": "done",
                                "descr": "Set to 1 by versat_ai when finished. 0 while running",
                                "mode": "R",
                                "n_bits": 1,
                                "rst_val": 0,
                                "log2n_items": 0,
                            },
                            {
                                "name": "metamodel_addr",
                                "descr": "Metamodel address",
                                "mode": "W",
                                "n_bits": 32,
                                "rst_val": 0,
                                "log2n_items": 0,
                            },
                            {
                                "name": "output_addr",
                                "descr": "Model address",
                                "mode": "W",
                                "n_bits": 32,
                                "rst_val": 0,
                                "log2n_items": 0,
                            },
                            {
                                "name": "temp_addr",
                                "descr": "Model address",
                                "mode": "W",
                                "n_bits": 32,
                                "rst_val": 0,
                                "log2n_items": 0,
                            },
                            {
                                "name": "model_addr",
                                "descr": "Model address",
                                "mode": "W",
                                "n_bits": 32,
                                "rst_val": 0,
                                "log2n_items": 0,
                            },
                            {
                                "name": "correctOutputs_addr",
                                "descr": "Correct output address",
                                "mode": "W",
                                "n_bits": 32,
                                "rst_val": 0,
                                "log2n_items": 0,
                            },
                            {
                                "name": "inputsVector_addr",
                                "descr": "Inputs address",
                                "mode": "W",
                                "n_bits": 32,
                                "rst_val": 0,
                                "log2n_items": 0,
                            },
                            # Versat-ai CPU control registers
                            {
                                "name": "rst",
                                "descr": "Resets CPU (1) or not (0).",
                                "mode": "W",
                                "n_bits": 1,
                                "rst_val": 0,  # Set to 1 to prevent versat from booting at startup
                                "log2n_items": 0,
                                "output": True,  # Generate dedicated output port with value of this CSR
                            },
                        ],
                    },
                ],
                "connect": {
                    "clk_en_rst_s": "clk_en_rst_s",
                    # Cbus connected automatically
                    "csrs_external_cbus_s": "csrs_cbus_s",
                    "rst_o": "rst",
                },
            }
        ]

    attributes_dict = {
        "title": "Versat-AI System",
        "description": "Accelerate AI Applications with Versat-AI.",
        "board_list": ["iob_aes_ku040_db_g"],
        "confs": [
            {
                "name": "USE_TESTER",
                "descr": "Wether we are compiling for Tester or not",
                "type": "C",
                "val": py_params["include_tester"],
                "min": "NA",
                "max": "NA",
            },
            {
                "name": "AXI_DATA_W",
                "descr": "Axi data width",
                "type": "P",
                "val": axi_data_w,
                "min": "1",
                "max": "1024",
            },
            {
                "name": "EXT_MEM_HEXFILE",
                "descr": "Firmware file name",
                "type": "D",
                "val": f'"{name}_firmware"',  # NOTE: The '"' inside are on purpose
                "min": "NA",
                "max": "NA",
            },
        ],
        "ports": [
            {
                # Add new rs232 port for uart
                "name": "rs232_m",
                "descr": "iob-system uart interface",
                "signals": {
                    "type": "rs232",
                },
            },
            {
                "name": "axi_m",
                "descr": "AXI manager interface for DDR memory",
                "signals": {
                    "type": "axi",
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": "AXI_ADDR_W",
                    "DATA_W": "AXI_DATA_W",
                    "LEN_W": "AXI_LEN_W",
                    "LOCK_W": 1,
                },
            },
            {
                "name": "csrs_cbus_s",
                "descr": "Control/Status Registers of versat-ai system (using regfileif).",
                "signals": {
                    "type": "iob",
                    "ADDR_W": 3,
                    "DATA_W": "AXI_DATA_W",
                },
            },
            # NOTE: Add other ports here.
        ],
        "wires": [
            {
                "name": "axi_periphs_cbus",
                "descr": "AXI bus for peripheral CSRs",
                "signals": {
                    "type": "axi",
                    "prefix": "periphs_",
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": 32 - xbar_sel_w,
                    "DATA_W": 32,
                    "LEN_W": "AXI_LEN_W",
                },
            },
            {
                "name": "unused_interconnect_bits",
                "descr": "Wires to connect to unused output bits of interconnect",
                "signals": [
                    {
                        "name": "unused_wires_0",
                        "width": 2,
                    },
                    {
                        "name": "unused_wires_1",
                        "width": 2,
                    },
                ],
            },
            {
                "name": "iob_periphs_cbus",
                "descr": "AXI-Lite bus for peripheral CSRs",
                "signals": {
                    "type": "iob",
                    "prefix": "periphs_",
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": 32 - xbar_sel_w,
                    "DATA_W": 32,
                    "LEN_W": "AXI_LEN_W",
                },
            },
            {
                "name": "bootrom_cbus",
                "descr": "iob-system boot controller data interface",
                "signals": {
                    "type": "axi",
                    "prefix": "bootrom_",
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": py_params["bootrom_addr_w"] + 1,  # +1 for csrs
                    "DATA_W": 32,
                    "LEN_W": "AXI_LEN_W",
                    "LOCK_W": "1",
                },
            },
            {
                "name": "narrow_axi",
                "descr": "Narrow axi wires",
                "signals": {
                    "type": "axi",
                    "prefix": "narrow_",
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": addr_w,
                    "DATA_W": 32,
                    "LEN_W": "AXI_LEN_W",
                    "LOCK_W": "1",
                },
            },
            {
                "name": "versat_axi",
                "descr": "Versat axi wires",
                "signals": {
                    "type": "axi",
                    "prefix": "versat_",
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": addr_w,
                    "DATA_W": "AXI_DATA_W",
                    "LEN_W": "AXI_LEN_W",
                    "LOCK_W": "1",
                },
            },
            {
                "name": "proper_axi",
                "descr": "AXI bus to connect SoC to interconnect",
                "signals": {
                    "type": "axi",
                    "prefix": "proper_",
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": 32,
                    "DATA_W": "AXI_DATA_W",
                    "LEN_W": "AXI_LEN_W",
                    "LOCK_W": 1,
                },
            },
            {
                "name": "delayed_cpu_d",
                "descr": "CPU_D delay",
                "signals": {
                    "type": "axi",
                    "prefix": "delay_d_",
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": addr_w,
                    "DATA_W": 32,
                    "LEN_W": "AXI_LEN_W",
                    "LOCK_W": "1",
                },
            },
            {
                "name": "delayed_cpu_i",
                "descr": "CPU_I delay",
                "signals": {
                    "type": "axi",
                    "prefix": "delay_i_",
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": addr_w,
                    "DATA_W": 32,
                    "LEN_W": "AXI_LEN_W",
                    "LOCK_W": "1",
                },
            },
            # CPU control wires
            {"name": "rst", "signals": [{"name": "sw_reset", "width": 1}]},
            # {  # FIXME: Connect this to CPU reset addr (or use preboot to jump to correct one) (or use address translator in tester).
            #     "name": "fw_base_addr",
            #     "signals": [{"name": "fw_base_addr", "width": addr_w}],
            # },
        ],
        "subblocks": subblocks,
        "sw_modules": [
            {
                "core_name": "iob_coverage_analyze",
                "instance_name": "iob_coverage_analyze_inst",
            },
        ],
    }
    if py_params["include_tester"]:
        attributes_dict["superblocks"] = [
            {  # Override tester with this one to pass custom sut py parameters
                "core_name": "iob_system_tester",
                "instance_name": "iob_system_tester",
                "sut_py_params": py_params,
                "dest_dir": "tester",
            },
        ]

    core_dict = {
        "version": "0.8.0",
        "parent": {
            "core_name": "iob_system",
            "system_attributes": attributes_dict,
            **py_params,
        },
    }

    return core_dict


#
# Utility functions
#


def update_params(params, py_params):
    # Default parameters
    new_params = params.copy()
    # Process python parameters
    for name, override_val in py_params.items():
        # If py param is a new parameter, append it to dict
        if name not in params:
            new_params[name] = override_val
            continue

        # Otherwise, py param will override default one
        default_val = params[name]
        # If py_param corresponds to a bool, and matches string "0", convert it to False
        # This is needed because running in python: bool("0") == True
        if type(default_val) is bool and override_val == "0":
            new_params[name] = False
        # Otherwise, convert py_param to correct type (for example: bool(override_val), int(override_val), etc)
        else:
            new_params[name] = type(default_val)(override_val)

    return new_params
