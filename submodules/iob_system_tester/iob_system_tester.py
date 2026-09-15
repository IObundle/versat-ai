# SPDX-FileCopyrightText: 2025 IObundle
#
# SPDX-License-Identifier: MIT

import os
import subprocess


def setup(py_params):
    mem_addr_w = 17  # 64 Kb
    name = "versat_ai_tester"
    addr_w = 32
    data_w = 32
    sut_py_params = py_params.get("sut_py_params", {})
    sut_mem_addr_w = sut_py_params.get("mem_addr_w", 30)

    # NOTE: With current configuration, Tester runs from intmem; SUT runs from extmem.

    init_mem = sut_py_params.get("tester_sim", False)

    # Set new default values for python parameters of iob_system (parent module)
    # List of iob_system python parameters available at: https://github.com/IObundle/py2hwsw/blob/main/py2hwsw/lib/iob_system/iob_system.py
    iob_system_default_overrides = {
        "init_mem": init_mem,
        "use_intmem": True,
        "use_extmem": True,
        "use_ethernet": False,
        "mem_addr_w": 30,
        "include_tester": False,  # This is already the tester. We don't want to include another one.
        "cpu": "iob_vexriscv",
        "fw_addr_w": 24,
    }

    py_params = update_params(iob_system_default_overrides, py_params)

    # SUT has custom 'tetster_use_ethernet' py param. If set, enable ethernet on this Tester system.
    if sut_py_params["tester_use_ethernet"]:
        py_params["use_ethernet"] = True

    # setup custom tester xbar to include more managers (SUT's extmem connection)
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
            "s0_axi_s": "delayed_cpu_i",
            "s1_axi_s": "delayed_cpu_d",
            "s2_axi_s": "translated_sut_axi",
            # Manager interfaces connected below
        },
        "addr_w": addr_w,
        "data_w": data_w,
        "lock_w": 1,
        "num_subordinates": 3,
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
        "use_intmem": (
            "int_mem_axi",
            [
                "{unused_m0_araddr_bits, int_mem_axi_araddr}",
                "{unused_m0_awaddr_bits, int_mem_axi_awaddr}",
            ],
        ),
        "use_extmem": (
            "axi_m",
            [
                "{unused_m1_araddr_bits, axi_araddr_o}",
                "{unused_m1_awaddr_bits, axi_awaddr_o}",
            ],
        ),
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
    # Connect xbar manager interfaces
    num_managers = 0
    for interface_connection in xbar_manager_interfaces.values():
        xbar_subblock["connect"] |= {f"m{num_managers}_axi_m": interface_connection}
        num_managers += 1
    xbar_subblock["num_managers"] = num_managers

    attributes_dict = {
        # Set "is_tester" attribute to generate Makefile and flows allowing to run this core as top module
        "is_tester": True,
        # Every attribute in this dictionary will override/append to the ones of the iob_system parent core.
        "board_list": [
            "iob_aes_ku040_db_g",
            # "iob_cyclonev_gt_dk",
            # "iob_zybo_z7",
        ],
        "confs": [
            {
                "name": "AXI_DATA_W",
                "descr": "Axi data width",
                "type": "P",
                "val": 32,
                "min": "32",
                "max": "32",
            },
        ],
        "wires": [
            {
                "name": "sut_rs232",
                "descr": "rs232 bus for SUT",
                "signals": {
                    "type": "rs232",
                    "prefix": "sut_",
                },
            },
            {
                "name": "sut_rs232_inverted",
                "descr": "Invert order of rs232 signals",
                "signals": [
                    {"name": "sut_rs232_txd"},
                    {"name": "sut_rs232_rxd"},
                    {"name": "sut_rs232_cts"},
                    {"name": "sut_rs232_rts"},
                ],
            },
            {
                "name": "delayed_cpu_d",
                "descr": "CPU_D delay",
                "signals": {
                    "type": "axi",
                    "prefix": "delay_d_",
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": addr_w,
                    "DATA_W": data_w,
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
                    "DATA_W": data_w,
                    "LEN_W": "AXI_LEN_W",
                    "LOCK_W": "1",
                },
            },
            {
                "name": "sut_axi",
                "descr": "Connect SUT (manager) to address_translator (subordinate)",
                "signals": {
                    "type": "axi",
                    "prefix": "sut_",
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": sut_mem_addr_w,
                    "DATA_W": data_w,
                    "LEN_W": "AXI_LEN_W",
                    "LOCK_W": "1",
                },
            },
            {
                "name": "translated_sut_axi",
                "descr": "Connect address_translator (manager) to xbar (subordinate)",
                "signals": {
                    "type": "axi",
                    "prefix": "translated_sut_",
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": addr_w,
                    "DATA_W": data_w,
                    "LEN_W": "AXI_LEN_W",
                    "LOCK_W": "1",
                },
            },
            # # GPIO wires for debug
            # {"name": "gpio_input", "signals": [{"name": "gpio_input", "width": 32}]},
            # {"name": "gpio_output", "signals": [{"name": "gpio_output", "width": 32}]},
        ],
        "subblocks": [
            xbar_subblock,
            {
                # Instantiate SUT (usually iob_system or a child of it)
                "core_name": py_params["issuer"]["original_name"],
                "instance_name": "SUT",
                "instance_description": "System Under Test (SUT) to be verified by this tester.",
                "is_peripheral": True,  # Only applies if SUT has CSRs (via regfileif).
                "parameters": {
                    "AXI_ID_W": "AXI_ID_W",
                    "AXI_LEN_W": "AXI_LEN_W",
                    "AXI_ADDR_W": "AXI_ADDR_W",
                    "AXI_DATA_W": "AXI_DATA_W",
                },
                "connect": {
                    "clk_en_rst_s": "clk_en_rst_s",
                    "axi_m": "sut_axi",
                    # Cbus (if any) is connected automatically
                    "rs232_m": "sut_rs232",
                },
            },
            {
                # Instantiate a UART core to communicate with SUT
                "core_name": "iob_uart",
                "instance_name": "UART1",
                "instance_description": "UART peripheral for communication with SUT.",
                "is_peripheral": True,
                "parameters": {},
                "connect": {
                    "clk_en_rst_s": "clk_en_rst_s",
                    # Cbus connected automatically
                    "rs232_m": "sut_rs232_inverted",
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
            # {
            #     # Instantiate a GPIO core for debug
            #     "core_name": "iob_gpio",
            #     "instance_name": "GPIO0",
            #     "instance_description": "Tester GPIO for debug",
            #     "is_peripheral": True,
            #     "parameters": {},
            #     "connect": {
            #         "clk_en_rst_s": "clk_en_rst_s",
            #         # Cbus connected automatically
            #         "input_0_i": "gpio_input",
            #         "output_0_o": "gpio_output",
            #     },
            # },
            # NOTE: Add other verification instruments (tester peripherals) here.
        ],
    }

    if py_params["use_extmem"]:
        attributes_dict["subblocks"] += [
            {
                "core_name": "iob_address_translator",
                "instance_name": "address_translator",
                "instance_description": "Translate addresses to access memory zones",
                "parameters": {
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": addr_w,
                    "DATA_W": data_w,
                    "LEN_W": "AXI_LEN_W",
                    "LOCK_W": "1",
                },
                "connect": {
                    "subordinate_s": (
                        "sut_axi",
                        [  # SUT only connects sut_mem_addr_w bits; Connect higher unused bits to zero.
                            f"{{{addr_w - sut_mem_addr_w}'b0, sut_axi_araddr}}",
                            f"{{{addr_w - sut_mem_addr_w}'b0, sut_axi_awaddr}}",
                        ],
                    ),
                    "manager_m": "translated_sut_axi",
                },
                "memory_zones": [
                    # (Start addr, End addr, Translation offset)
                    (0x00000000, 0x1FFFFFFF, 0x40000000),
                ],
            },
        ]

    # Py2hwsw dictionary describing current core
    core_dict = {
        "parent": {
            # Tester is a child core of iob_system: https://github.com/IObundle/py2hwsw/tree/main/py2hwsw/lib/hardware/iob_system
            # Tester will inherit all attributes/files from the iob_system core.
            "core_name": "iob_system",
            # Every parameter in the lines below will be passed to the iob_system parent core.
            **py_params,
            "system_attributes": attributes_dict,
        },
    }

    # # Symlink specific sources from SUT's software to Tester's software folder
    # # but only if setting up tester (not during targets like clean)
    if py_params.get("py2hwsw_target", "") == "setup":
        dst = f"{py_params['build_dir']}/tester/software/src/"
        os.makedirs(dst, exist_ok=True)
        src = f"../../../software/src/"
        for src_file in [
            "iob_regfileif_csrs_conf.h",
            "iob_regfileif_csrs.h",
            "iob_regfileif_csrs.c",
            "iob_regfileif_conf.h",
            # "versat_ai_conf.h",
        ]:
            if not os.path.exists(f"{dst}{src_file}"):
                os.symlink(
                    f"{src}{src_file}",
                    f"{dst}{src_file}",
                )

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
