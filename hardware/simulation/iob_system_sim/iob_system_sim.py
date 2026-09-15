# SPDX-FileCopyrightText: 2025 IObundle
#
# SPDX-License-Identifier: MIT


def setup(py_params_dict):
    params = py_params_dict["iob_system_params"]
    addr_w = params["mem_addr_w"]

    axi_data_w = 0
    for conf in params["system_attributes"]["confs"]:
        if conf.get("name", "") == "AXI_DATA_W":
            axi_data_w = conf.get("val", 0)
            break

    assert axi_data_w > 0

    axi_offset = 0
    if axi_data_w == 32:
        axi_offset = 2
    if axi_data_w == 64:
        axi_offset = 3
    if axi_data_w == 128:
        axi_offset = 4
    if axi_data_w == 256:
        axi_offset = 5
    if axi_data_w == 512:
        axi_offset = 6

    assert axi_offset > 0

    # Size of RAM for ethernet's dma
    ETH_RAM_ADDR_W = 14

    tb_peripherals = ["iob_uart"]
    if params["use_ethernet"]:
        tb_peripherals += ["iob_eth"]

    periph_sel_bits = (len(tb_peripherals) - 1).bit_length()
    periph_addr_w = 32 - periph_sel_bits

    attributes_dict = {
        "name": "iob_uut",
        "generate_hw": True,
        "confs": [
            {
                "name": "AXI_ID_W",
                "descr": "AXI ID bus width",
                "type": "D",
                "val": "4",
            },
            {
                "name": "AXI_LEN_W",
                "descr": "AXI burst length width",
                "type": "D",
                "val": "8",
            },
            {
                "name": "AXI_ADDR_W",
                "descr": "AXI address bus width",
                "type": "D",
                "val": params["mem_addr_w"],
            },
            {
                "name": "AXI_DATA_W",
                "descr": "AXI data bus width",
                "type": "D",
                "val": axi_data_w,
            },
            {
                "name": "BAUD",
                "descr": "UART baud rate",
                "type": "D",
                "val": "3000000",
            },
            {
                "name": "FREQ",
                "descr": "Clock frequency",
                "type": "D",
                "val": "100000000",
            },
            {
                "name": "SIMULATION",
                "descr": "Simulation flag",
                "type": "D",
                "val": "1",
            },
        ],
    }

    #
    # Ports
    #
    attributes_dict["ports"] = [
        {
            "name": "clk_en_rst_s",
            "descr": "Clock, clock enable and reset",
            "signals": {
                "type": "iob_clk",
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
            "name": "tb_s",
            "descr": "Testbench iob interface",
            "signals": {
                "type": "iob",
                "ADDR_W": 32,
            },
        },
    ]

    #
    # Wires
    #
    attributes_dict["wires"] = [
        {
            "name": "clk",
            "descr": "Clock signal",
            "signals": [
                {"name": "clk_i"},
            ],
        },
        {
            "name": "rst",
            "descr": "Reset signal",
            "signals": [
                {"name": "arst_i"},
            ],
        },
        {
            "name": "rs232",
            "descr": "rs232 bus",
            "signals": {
                "type": "rs232",
            },
        },
        {
            "name": "rs232_invert",
            "descr": "Invert order of rs232 signals",
            "signals": [
                {"name": "rs232_txd"},
                {"name": "rs232_rxd"},
                {"name": "rs232_cts"},
                {"name": "rs232_rts"},
            ],
        },
    ]
    if len(tb_peripherals) > 1:
        attributes_dict["wires"] += [
            {
                "name": "uart_cbus",
                "descr": "UART CSR bus",
                "signals": {
                    "type": "iob",
                    "prefix": "uart_",
                    "ADDR_W": periph_addr_w,
                },
            },
        ]
    if params["use_extmem"]:
        attributes_dict["wires"] += [
            {
                "name": "uut_axi",
                "descr": "AXI bus to connect SoC to interconnect",
                "signals": {
                    "type": "axi",
                    "prefix": "uut_",
                    "ID_W": "AXI_ID_W",
                    "ADDR_W": "AXI_ADDR_W",
                    "DATA_W": "AXI_DATA_W",
                    "LEN_W": "AXI_LEN_W",
                    "LOCK_W": 1,
                },
            },
            #            {
            #                "name": "delayed_uut_axi",
            #                "descr": "AXI bus to connect SoC to interconnect",
            #                "signals": {
            #                    "type": "axi",
            #                    "prefix": "delayed_uut_",
            #                    "ID_W": "AXI_ID_W",
            #                    "ADDR_W": "AXI_ADDR_W",
            #                    "DATA_W": "AXI_DATA_W",
            #                    "LEN_W": "AXI_LEN_W",
            #                    "LOCK_W": 1,
            #                },
            #            },
            {
                "name": "axi_ram_mem",
                "descr": "Connect axi_ram to 'iob_ram_t2p_be' memory",
                "signals": {
                    "type": "ram_t2p_be",
                    "prefix": "ext_mem_",
                    "ADDR_W": f"AXI_ADDR_W - {axi_offset}",
                    "DATA_W": "AXI_DATA_W",
                },
            },
        ]

    if params["use_ethernet"]:
        attributes_dict["wires"] += [
            {
                "name": "eth_cbus",
                "descr": "Ethernet CSR bus",
                "signals": {
                    "type": "iob",
                    "prefix": "eth_",
                    "ADDR_W": periph_addr_w,
                },
            },
            {
                "name": "unused_eth_axi",
                "descr": "Ethernet AXI bus (unused: tesbench uses eth without DMA)",
                "signals": {
                    "type": "axi",
                    "prefix": "eth_",
                    "ADDR_W": ETH_RAM_ADDR_W,
                    "ID_W": "AXI_ID_W",
                    "LEN_W": "AXI_LEN_W",
                },
            },
            {
                "name": "phy_rstn",
                "descr": "",
                "signals": [
                    {
                        "name": "phy_rstn",
                        "width": "1",
                        "descr": "Issuer ethernet reset signal for PHY.",
                    },
                ],
            },
            {
                "name": "tb_phy_rstn",
                "descr": "",
                "signals": [
                    {
                        "name": "tb_phy_rstn",
                        "width": "1",
                        "descr": "Testbench ethernet reset signal for PHY.",
                    },
                ],
            },
            {
                "name": "mii",
                "descr": "Ethernet MII interface",
                "signals": {
                    "type": "mii",
                },
            },
            {
                "name": "mii_invert",
                "descr": "Invert RX and TX signals of ethernet MII bus",
                "signals": [
                    {"name": "mii_tx_clk"},
                    {"name": "mii_rxd"},
                    {"name": "mii_rx_dv"},
                    {"name": "mii_rx_er"},
                    {"name": "mii_rx_clk"},
                    {"name": "mii_txd"},
                    {"name": "mii_tx_en"},
                    {"name": "mii_tx_er"},
                    {"name": "mii_crs"},
                    {"name": "mii_col"},
                    # Create new management signals for testbench eth
                    {"name": "tb_mii_mdio", "width": "1"},
                    {"name": "tb_mii_mdc", "width": "1"},
                ],
            },
            {
                "name": "eth_int",
                "descr": "Ethernet interrupt",
                "signals": [
                    {"name": "eth_interrupt"},
                ],
            },
        ]

    #
    # Blocks
    #
    attributes_dict["subblocks"] = [
        {
            "core_name": py_params_dict["issuer"]["original_name"],
            "instance_name": py_params_dict["issuer"]["original_name"],
            "instance_description": "IOb-SoC memory wrapper",
            "parameters": {
                "AXI_ID_W": "AXI_ID_W",
                "AXI_LEN_W": "AXI_LEN_W",
                "AXI_ADDR_W": "AXI_ADDR_W",
                "AXI_DATA_W": axi_data_w,
                "SIMULATION": "SIMULATION",
            },
            "connect": {
                "clk_en_rst_s": "clk_en_rst_s",
                "rs232_m": "rs232",
                "axi_m": "uut_axi",
            },
            "dest_dir": "hardware/common_src",
        },
    ]

    if params["use_ethernet"]:
        attributes_dict["subblocks"][-1]["connect"].update({"mii_io": "mii"})
        attributes_dict["subblocks"][-1]["connect"].update({"phy_rstn_o": "phy_rstn"})
    if len(tb_peripherals) > 1:
        attributes_dict["subblocks"] += [
            {
                "core_name": "iob_split",
                "name": "tb_pbus_split",
                "instance_name": "iob_pbus_split",
                "instance_description": "Split between testbench peripherals",
                "connect": {
                    "clk_en_rst_s": "clk_en_rst_s",
                    "reset_i": "split_reset",
                    "s_s": "tb_s",
                    "m_0_m": "uart_cbus",
                },
                "num_managers": 1,
                "addr_w": 32,
            },
        ]
    if params["use_ethernet"]:
        subordinate_num = attributes_dict["subblocks"][-1]["num_managers"]
        attributes_dict["subblocks"][-1]["num_managers"] += 1
        attributes_dict["subblocks"][-1]["connect"] |= {
            f"m_{subordinate_num}_m": "eth_cbus",
        }

    # Connect ethernet and its RAM to pbus
    attributes_dict["subblocks"] += [
        #        {
        #            "core_name": "versat_axi_simdelay",
        #            "instance_name": "delay",
        #            "instance_description": "Delay",
        #            "connect": {
        #                "clk_en_rst_s": "clk_en_rst_s",
        #                "axi_m": "delayed_uut_axi",
        #                "axi_s": "uut_axi",
        #            },
        #        },
        {
            "core_name": "iob_uart",
            "instance_name": "uart_tb",
            "instance_description": "Testbench uart core",
            "csr_if": "iob",
            "connect": {
                "clk_en_rst_s": "clk_en_rst_s",
                "csrs_cbus_s": ("uart_cbus", ["uart_iob_addr[3:0]"]),
                "rs232_m": "rs232_invert",
            },
        },
    ]

    if len(tb_peripherals) == 1:
        # Connect uart directly to tb_s port if there is no tb_pbus_split
        attributes_dict["subblocks"][-1]["connect"].update(
            {"csrs_cbus_s": ("tb_s", ["iob_addr_i[3:0]"])}
        )

    if params["use_extmem"]:
        attributes_dict["subblocks"] += [
            {
                "core_name": "iob_axi_ram",
                "instance_name": "ddr_model_mem",
                "instance_description": "External memory",
                "parameters": {
                    "ID_WIDTH": "AXI_ID_W",
                    "ADDR_WIDTH": "AXI_ADDR_W",
                    "DATA_WIDTH": "AXI_DATA_W",
                },
                "connect": {
                    "clk_i": "clk",
                    "rst_i": "rst",
                    "axi_s": (
                        "uut_axi",
                        [
                            "{1'b0, uut_axi_arlock}",
                            "{1'b0, uut_axi_awlock}",
                        ],
                    ),
                    "external_mem_bus_m": "axi_ram_mem",
                },
            },
            {
                "core_name": "iob_ram_t2p_be",
                "instance_name": "iob_ram_t2p_be_inst",
                "parameters": {
                    "ADDR_W": f"AXI_ADDR_W - {axi_offset}",
                    "DATA_W": "AXI_DATA_W",
                },
                "connect": {
                    "ram_t2p_be_s": "axi_ram_mem",
                },
            },
        ]
        if params["init_mem"] and not params["use_intmem"]:
            attributes_dict["subblocks"][-1]["parameters"].update(
                {
                    "HEXFILE": f'"{params["name"]}_firmware"',
                }
            )

    if params["use_ethernet"]:
        attributes_dict["subblocks"] += [
            {
                "core_name": "iob_eth",
                "instance_name": "eth_tb",
                "parameters": {
                    "AXI_ID_W": "AXI_ID_W",
                    "AXI_LEN_W": "AXI_LEN_W",
                    "AXI_ADDR_W": ETH_RAM_ADDR_W,
                    "AXI_DATA_W": 32,
                    "DATA_W": 32,
                },
                "connect": {
                    "clk_en_rst_s": "clk_en_rst_s",
                    "csrs_cbus_s": ("eth_cbus", ["eth_iob_addr[11:0]"]),
                    "axi_m": "unused_eth_axi",
                    "inta_o": "eth_int",
                    "phy_rstn_o": "tb_phy_rstn",
                    "mii_io": "mii_invert",
                },
            },
        ]
    #
    # Snippets
    #
    attributes_dict["snippets"] = []
    if params["use_ethernet"]:
        attributes_dict["snippets"] += [
            {
                "verilog_code": """
    //ethernet clock: 4x slower than system clock
    reg [1:0] eth_cnt = 2'b0;
    reg       eth_clk;

    always @(posedge clk_i) begin
      eth_cnt <= eth_cnt + 1'b1;
      eth_clk <= eth_cnt[1];
    end

    // Set ethernet AXI inputs to low
    assign eth_axi_awready = 1'b0;
    assign eth_axi_wready  = 1'b0;
    assign eth_axi_bid     = {AXI_ID_W{1'b0}};
    assign eth_axi_bresp   = 2'b0;
    assign eth_axi_bvalid  = 1'b0;
    assign eth_axi_arready = 1'b0;
    assign eth_axi_rid     = {AXI_ID_W{1'b0}};
    assign eth_axi_rdata   = {AXI_DATA_W{1'b0}};
    assign eth_axi_rresp   = 2'b0;
    assign eth_axi_rlast   = 1'b0;
    assign eth_axi_rvalid  = 1'b0;

    // Connect ethernet MII signals
    assign mii_tx_clk       = eth_clk;
    assign mii_rx_clk       = eth_clk;
    assign mii_col          = 1'b0;
    assign mii_crs          = 1'b0;

""",
            },
        ]

    # Calculate and print testbench peripheral memory map
    print("------------------------------------------------------")
    print("Testbench memory map:")
    current_addr = 0
    for peripheral in tb_peripherals:
        print(
            f"[0x{current_addr:08x}-0x{(current_addr+(1<<periph_addr_w)-1):08x}]: {peripheral} ({periph_addr_w} bits)"
        )
        current_addr += 1 << periph_addr_w
    print("------------------------------------------------------")

    return attributes_dict
