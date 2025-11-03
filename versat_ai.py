# SPDX-FileCopyrightText: 2025 IObundle
#
# SPDX-License-Identifier: MIT


def setup(py_params: dict):
    # Py2hwsw dictionary describing current core
    mem_addr_w = 20
    name = "versat_ai"
    addr_w = 32
    data_w = 32

    # Set new default values for python parameters of iob_system (parent module)
    # List of iob_system python parameters available at: https://github.com/IObundle/py2hwsw/blob/main/py2hwsw/lib/iob_system/iob_system.py
    iob_system_default_overrides = {
        "use_intmem": False,
        "use_extmem": True,
        "use_ethernet": False,
        "mem_addr_w": mem_addr_w,
        "include_tester": False,
        "cpu": "iob_vexriscv",
        "fw_addr_w": 19,
    }

    py_params = {**iob_system_default_overrides, **py_params}

    # setup custom xbar
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
            "s0_axi_s": "cpu_ibus",
            "s1_axi_s": "cpu_dbus",
            "s2_axi_s": "versat_axi",
            # Manager interfaces connected below
        },
        "addr_w": addr_w,
        "data_w": data_w,
        "lock_w": 1,
        "num_subordinates": 3,
    }
    xbar_manager_interfaces = {
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
        "title": "Versat-AI System",
        "description": "Accelerate AI Applications with Versat-AI.",
        "board_list": [
            "iob_aes_ku040_db_g",
            "iob_cyclonev_gt_dk",
            "iob_zybo_z7",
        ],
        "confs": [
            # {   TODO: is this needed?
            #     "name": "INT_MEM_HEXFILE",
            #     "descr": "Firmware file name",
            #     "type": "D",
            #     "val": f'"{name}_firmware"',  # NOTE: The '"' inside are on purpose
            #     "min": "NA",
            #     "max": "NA",
            # },
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
            # NOTE: Add other ports here.
        ],
        "wires": [
            {
                "name": "versat_axi",
                "descr": "Versat axi wires",
                "signals": {
                    "type": "axi",
                    "prefix": "versat_",
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": addr_w,
                    "DATA_W": data_w,
                    "LEN_W": "AXI_LEN_W",
                    "LOCK_W": "1",
                },
            },
        ],
        "subblocks": [
            xbar_subblock,
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
                "parameters": {},
                "connect": {"axi_out_m": "versat_axi"},
            },
            # NOTE: Add other components/peripherals here.
        ],
        "sw_modules": [
            {
                "core_name": "iob_coverage_analyze",
                "instance_name": "iob_coverage_analyze_inst",
            },
        ],
    }

    core_dict = {
        "version": "0.8",
        "parent": {
            "core_name": "iob_system",
            "system_attributes": attributes_dict,
            **py_params,
        },
    }

    return core_dict
