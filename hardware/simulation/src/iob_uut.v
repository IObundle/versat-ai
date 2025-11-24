// SPDX-FileCopyrightText: 2025 IObundle, Lda
//
// SPDX-License-Identifier: MIT
//
// Py2HWSW Version 0.81 has generated this code (https://github.com/IObundle/py2hwsw).

`timescale 1ns / 1ps
`include "iob_uut_conf.vh"

module iob_uut #(
    parameter AXI_ID_W = `IOB_UUT_AXI_ID_W,  // Don't change this parameter value!
    parameter AXI_LEN_W = `IOB_UUT_AXI_LEN_W,  // Don't change this parameter value!
    parameter AXI_ADDR_W = `IOB_UUT_AXI_ADDR_W,  // Don't change this parameter value!
    parameter AXI_DATA_W = `IOB_UUT_AXI_DATA_W,  // Don't change this parameter value!
    parameter BAUD = `IOB_UUT_BAUD,  // Don't change this parameter value!
    parameter FREQ = `IOB_UUT_FREQ,  // Don't change this parameter value!
    parameter SIMULATION = `IOB_UUT_SIMULATION  // Don't change this parameter value!
) (
    // clk_en_rst_s: Clock, clock enable and reset
    input clk_i,
    input cke_i,
    input arst_i,
    // tb_s: Testbench iob interface
    input iob_valid_i,
    input [32-1:0] iob_addr_i,
    input [32-1:0] iob_wdata_i,
    input [32/8-1:0] iob_wstrb_i,
    output iob_rvalid_o,
    output [32-1:0] iob_rdata_o,
    output iob_ready_o
);

// rs232 bus
    wire rs232_rxd;
    wire rs232_txd;
    wire rs232_rts;
    wire rs232_cts;
// UART CSR bus
    wire uart_iob_valid;
    wire [31-1:0] uart_iob_addr;
    wire [32-1:0] uart_iob_wdata;
    wire [32/8-1:0] uart_iob_wstrb;
    wire uart_iob_rvalid;
    wire [32-1:0] uart_iob_rdata;
    wire uart_iob_ready;
// AXI bus to connect SoC to interconnect
    wire [AXI_ADDR_W-1:0] axi_araddr;
    wire axi_arvalid;
    wire axi_arready;
    wire [AXI_DATA_W-1:0] axi_rdata;
    wire [2-1:0] axi_rresp;
    wire axi_rvalid;
    wire axi_rready;
    wire [AXI_ID_W-1:0] axi_arid;
    wire [AXI_LEN_W-1:0] axi_arlen;
    wire [3-1:0] axi_arsize;
    wire [2-1:0] axi_arburst;
    wire axi_arlock;
    wire [4-1:0] axi_arcache;
    wire [4-1:0] axi_arqos;
    wire [AXI_ID_W-1:0] axi_rid;
    wire axi_rlast;
    wire [AXI_ADDR_W-1:0] axi_awaddr;
    wire axi_awvalid;
    wire axi_awready;
    wire [AXI_DATA_W-1:0] axi_wdata;
    wire [AXI_DATA_W/8-1:0] axi_wstrb;
    wire axi_wvalid;
    wire axi_wready;
    wire [2-1:0] axi_bresp;
    wire axi_bvalid;
    wire axi_bready;
    wire [AXI_ID_W-1:0] axi_awid;
    wire [AXI_LEN_W-1:0] axi_awlen;
    wire [3-1:0] axi_awsize;
    wire [2-1:0] axi_awburst;
    wire axi_awlock;
    wire [4-1:0] axi_awcache;
    wire [4-1:0] axi_awqos;
    wire axi_wlast;
    wire [AXI_ID_W-1:0] axi_bid;
// Connect axi_ram to 'iob_ram_t2p_be' memory
    wire ext_mem_clk;
    wire ext_mem_r_en;
    wire [AXI_ADDR_W - 2-1:0] ext_mem_r_addr;
    wire [32-1:0] ext_mem_r_data;
    wire [32/8-1:0] ext_mem_w_strb;
    wire [AXI_ADDR_W - 2-1:0] ext_mem_w_addr;
    wire [32-1:0] ext_mem_w_data;
// Ethernet CSR bus
    wire eth_iob_valid;
    wire [31-1:0] eth_iob_addr;
    wire [32-1:0] eth_iob_wdata;
    wire [32/8-1:0] eth_iob_wstrb;
    wire eth_iob_rvalid;
    wire [32-1:0] eth_iob_rdata;
    wire eth_iob_ready;
// Ethernet AXI bus (unused: tesbench uses eth without DMA)
    wire [14-1:0] eth_axi_araddr;
    wire eth_axi_arvalid;
    wire eth_axi_arready;
    wire [32-1:0] eth_axi_rdata;
    wire [2-1:0] eth_axi_rresp;
    wire eth_axi_rvalid;
    wire eth_axi_rready;
    wire [AXI_ID_W-1:0] eth_axi_arid;
    wire [AXI_LEN_W-1:0] eth_axi_arlen;
    wire [3-1:0] eth_axi_arsize;
    wire [2-1:0] eth_axi_arburst;
    wire [2-1:0] eth_axi_arlock;
    wire [4-1:0] eth_axi_arcache;
    wire [4-1:0] eth_axi_arqos;
    wire [AXI_ID_W-1:0] eth_axi_rid;
    wire eth_axi_rlast;
    wire [14-1:0] eth_axi_awaddr;
    wire eth_axi_awvalid;
    wire eth_axi_awready;
    wire [32-1:0] eth_axi_wdata;
    wire [32/8-1:0] eth_axi_wstrb;
    wire eth_axi_wvalid;
    wire eth_axi_wready;
    wire [2-1:0] eth_axi_bresp;
    wire eth_axi_bvalid;
    wire eth_axi_bready;
    wire [AXI_ID_W-1:0] eth_axi_awid;
    wire [AXI_LEN_W-1:0] eth_axi_awlen;
    wire [3-1:0] eth_axi_awsize;
    wire [2-1:0] eth_axi_awburst;
    wire [2-1:0] eth_axi_awlock;
    wire [4-1:0] eth_axi_awcache;
    wire [4-1:0] eth_axi_awqos;
    wire eth_axi_wlast;
    wire [AXI_ID_W-1:0] eth_axi_bid;
    wire phy_rstn;
    wire tb_phy_rstn;
// Ethernet MII interface
    wire mii_tx_clk;
    wire [4-1:0] mii_txd;
    wire mii_tx_en;
    wire mii_tx_er;
    wire mii_rx_clk;
    wire [4-1:0] mii_rxd;
    wire mii_rx_dv;
    wire mii_rx_er;
    wire mii_crs;
    wire mii_col;
    wire mii_mdio;
    wire mii_mdc;
// Invert RX and TX signals of ethernet MII bus
    wire tb_mii_mdio;
    wire tb_mii_mdc;
// Ethernet interrupt
    wire eth_interrupt;
// Reset signal
    wire rst;


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



        // IOb-SoC memory wrapper
        versat_ai_mwrap #(
        .AXI_ID_W(AXI_ID_W),
        .AXI_LEN_W(AXI_LEN_W),
        .AXI_ADDR_W(AXI_ADDR_W),
        .AXI_DATA_W(AXI_DATA_W)
    ) iob_memwrapper (
            // clk_en_rst_s port: Clock, clock enable and reset
        .clk_i(clk_i),
        .cke_i(cke_i),
        .arst_i(arst_i),
        // rs232_m port: iob-system uart interface
        .rs232_rxd_i(rs232_rxd),
        .rs232_txd_o(rs232_txd),
        .rs232_rts_o(rs232_rts),
        .rs232_cts_i(rs232_cts),
        // mii_io port: Ethernet MII interface
        .mii_tx_clk_i(mii_tx_clk),
        .mii_txd_o(mii_txd),
        .mii_tx_en_o(mii_tx_en),
        .mii_tx_er_o(mii_tx_er),
        .mii_rx_clk_i(mii_rx_clk),
        .mii_rxd_i(mii_rxd),
        .mii_rx_dv_i(mii_rx_dv),
        .mii_rx_er_i(mii_rx_er),
        .mii_crs_i(mii_crs),
        .mii_col_i(mii_col),
        .mii_mdio_io(mii_mdio),
        .mii_mdc_o(mii_mdc),
        .phy_rstn_o(),
        // axi_m port: AXI manager interface for DDR memory
        .axi_araddr_o(axi_araddr),
        .axi_arvalid_o(axi_arvalid),
        .axi_arready_i(axi_arready),
        .axi_rdata_i(axi_rdata),
        .axi_rresp_i(axi_rresp),
        .axi_rvalid_i(axi_rvalid),
        .axi_rready_o(axi_rready),
        .axi_arid_o(axi_arid),
        .axi_arlen_o(axi_arlen),
        .axi_arsize_o(axi_arsize),
        .axi_arburst_o(axi_arburst),
        .axi_arlock_o(axi_arlock),
        .axi_arcache_o(axi_arcache),
        .axi_arqos_o(axi_arqos),
        .axi_rid_i(axi_rid),
        .axi_rlast_i(axi_rlast),
        .axi_awaddr_o(axi_awaddr),
        .axi_awvalid_o(axi_awvalid),
        .axi_awready_i(axi_awready),
        .axi_wdata_o(axi_wdata),
        .axi_wstrb_o(axi_wstrb),
        .axi_wvalid_o(axi_wvalid),
        .axi_wready_i(axi_wready),
        .axi_bresp_i(axi_bresp),
        .axi_bvalid_i(axi_bvalid),
        .axi_bready_o(axi_bready),
        .axi_awid_o(axi_awid),
        .axi_awlen_o(axi_awlen),
        .axi_awsize_o(axi_awsize),
        .axi_awburst_o(axi_awburst),
        .axi_awlock_o(axi_awlock),
        .axi_awcache_o(axi_awcache),
        .axi_awqos_o(axi_awqos),
        .axi_wlast_o(axi_wlast),
        .axi_bid_i(axi_bid)
        );

            // Split between testbench peripherals
        tb_pbus_split iob_pbus_split (
            // clk_en_rst_s port: Clock, clock enable and async reset
        .clk_i(clk_i),
        .cke_i(cke_i),
        .arst_i(arst_i),
        // reset_i port: Reset signal
        .rst_i(rst),
        // input_s port: Split input
        .input_iob_valid_i(iob_valid_i),
        .input_iob_addr_i(iob_addr_i),
        .input_iob_wdata_i(iob_wdata_i),
        .input_iob_wstrb_i(iob_wstrb_i),
        .input_iob_rvalid_o(iob_rvalid_o),
        .input_iob_rdata_o(iob_rdata_o),
        .input_iob_ready_o(iob_ready_o),
        // output_0_m port: Split output interface
        .output0_iob_valid_o(uart_iob_valid),
        .output0_iob_addr_o(uart_iob_addr),
        .output0_iob_wdata_o(uart_iob_wdata),
        .output0_iob_wstrb_o(uart_iob_wstrb),
        .output0_iob_rvalid_i(uart_iob_rvalid),
        .output0_iob_rdata_i(uart_iob_rdata),
        .output0_iob_ready_i(uart_iob_ready),
        // output_1_m port: Split output interface
        .output1_iob_valid_o(eth_iob_valid),
        .output1_iob_addr_o(eth_iob_addr),
        .output1_iob_wdata_o(eth_iob_wdata),
        .output1_iob_wstrb_o(eth_iob_wstrb),
        .output1_iob_rvalid_i(eth_iob_rvalid),
        .output1_iob_rdata_i(eth_iob_rdata),
        .output1_iob_ready_i(eth_iob_ready)
        );

            // Testbench uart core
        iob_uart uart_tb (
            // clk_en_rst_s port: Clock, clock enable and reset
        .clk_i(clk_i),
        .cke_i(cke_i),
        .arst_i(arst_i),
        // iob_csrs_cbus_s port: Control and Status Registers interface (auto-generated)
        .iob_csrs_iob_valid_i(uart_iob_valid),
        .iob_csrs_iob_addr_i(uart_iob_addr[2:0]),
        .iob_csrs_iob_wdata_i(uart_iob_wdata),
        .iob_csrs_iob_wstrb_i(uart_iob_wstrb),
        .iob_csrs_iob_rvalid_o(uart_iob_rvalid),
        .iob_csrs_iob_rdata_o(uart_iob_rdata),
        .iob_csrs_iob_ready_o(uart_iob_ready),
        // rs232_m port: RS232 interface
        .rs232_rxd_i(rs232_txd),
        .rs232_txd_o(rs232_rxd),
        .rs232_rts_o(rs232_cts),
        .rs232_cts_i(rs232_rts)
        );

            // External memory
        iob_axi_ram #(
        .ID_WIDTH(AXI_ID_W),
        .ADDR_WIDTH(AXI_ADDR_W),
        .DATA_WIDTH(AXI_DATA_W)
    ) ddr_model_mem (
            // clk_i port: Clock
        .clk_i(clk_i),
        // rst_i port: Synchronous reset
        .rst_i(arst_i),
        // axi_s port: AXI interface
        .axi_araddr_i(axi_araddr),
        .axi_arvalid_i(axi_arvalid),
        .axi_arready_o(axi_arready),
        .axi_rdata_o(axi_rdata),
        .axi_rresp_o(axi_rresp),
        .axi_rvalid_o(axi_rvalid),
        .axi_rready_i(axi_rready),
        .axi_arid_i(axi_arid),
        .axi_arlen_i(axi_arlen),
        .axi_arsize_i(axi_arsize),
        .axi_arburst_i(axi_arburst),
        .axi_arlock_i({1'b0, axi_arlock}),
        .axi_arcache_i(axi_arcache),
        .axi_arqos_i(axi_arqos),
        .axi_rid_o(axi_rid),
        .axi_rlast_o(axi_rlast),
        .axi_awaddr_i(axi_awaddr),
        .axi_awvalid_i(axi_awvalid),
        .axi_awready_o(axi_awready),
        .axi_wdata_i(axi_wdata),
        .axi_wstrb_i(axi_wstrb),
        .axi_wvalid_i(axi_wvalid),
        .axi_wready_o(axi_wready),
        .axi_bresp_o(axi_bresp),
        .axi_bvalid_o(axi_bvalid),
        .axi_bready_i(axi_bready),
        .axi_awid_i(axi_awid),
        .axi_awlen_i(axi_awlen),
        .axi_awsize_i(axi_awsize),
        .axi_awburst_i(axi_awburst),
        .axi_awlock_i({1'b0, axi_awlock}),
        .axi_awcache_i(axi_awcache),
        .axi_awqos_i(axi_awqos),
        .axi_wlast_i(axi_wlast),
        .axi_bid_o(axi_bid),
        // external_mem_bus_m port: Port for connection to external 'iob_ram_t2p_be' memory
        .ext_mem_clk_o(ext_mem_clk),
        .ext_mem_r_en_o(ext_mem_r_en),
        .ext_mem_r_addr_o(ext_mem_r_addr),
        .ext_mem_r_data_i(ext_mem_r_data),
        .ext_mem_w_strb_o(ext_mem_w_strb),
        .ext_mem_w_addr_o(ext_mem_w_addr),
        .ext_mem_w_data_o(ext_mem_w_data)
        );

            // Default description
        iob_ram_t2p_be #(
        .ADDR_W(AXI_ADDR_W - 2),
        .DATA_W(AXI_DATA_W)
    ) iob_ram_t2p_be_inst (
            // ram_t2p_be_s port: RAM interface
        .clk_i(ext_mem_clk),
        .r_en_i(ext_mem_r_en),
        .r_addr_i(ext_mem_r_addr),
        .r_data_o(ext_mem_r_data),
        .w_strb_i(ext_mem_w_strb),
        .w_addr_i(ext_mem_w_addr),
        .w_data_i(ext_mem_w_data)
        );

            // Default description
        iob_eth #(
        .AXI_ID_W(AXI_ID_W),
        .AXI_LEN_W(AXI_LEN_W),
        .AXI_ADDR_W(14),
        .AXI_DATA_W(32)
    ) eth_tb (
            // clk_en_rst_s port: Clock, clock enable and reset
        .clk_i(clk_i),
        .cke_i(cke_i),
        .arst_i(arst_i),
        // iob_csrs_cbus_s port: Control and Status Registers interface (auto-generated)
        .iob_csrs_iob_valid_i(eth_iob_valid),
        .iob_csrs_iob_addr_i(eth_iob_addr[11:0]),
        .iob_csrs_iob_wdata_i(eth_iob_wdata),
        .iob_csrs_iob_wstrb_i(eth_iob_wstrb),
        .iob_csrs_iob_rvalid_o(eth_iob_rvalid),
        .iob_csrs_iob_rdata_o(eth_iob_rdata),
        .iob_csrs_iob_ready_o(eth_iob_ready),
        // axi_m port: AXI manager interface for external memory
        .axi_araddr_o(eth_axi_araddr),
        .axi_arvalid_o(eth_axi_arvalid),
        .axi_arready_i(eth_axi_arready),
        .axi_rdata_i(eth_axi_rdata),
        .axi_rresp_i(eth_axi_rresp),
        .axi_rvalid_i(eth_axi_rvalid),
        .axi_rready_o(eth_axi_rready),
        .axi_arid_o(eth_axi_arid),
        .axi_arlen_o(eth_axi_arlen),
        .axi_arsize_o(eth_axi_arsize),
        .axi_arburst_o(eth_axi_arburst),
        .axi_arlock_o(eth_axi_arlock),
        .axi_arcache_o(eth_axi_arcache),
        .axi_arqos_o(eth_axi_arqos),
        .axi_rid_i(eth_axi_rid),
        .axi_rlast_i(eth_axi_rlast),
        .axi_awaddr_o(eth_axi_awaddr),
        .axi_awvalid_o(eth_axi_awvalid),
        .axi_awready_i(eth_axi_awready),
        .axi_wdata_o(eth_axi_wdata),
        .axi_wstrb_o(eth_axi_wstrb),
        .axi_wvalid_o(eth_axi_wvalid),
        .axi_wready_i(eth_axi_wready),
        .axi_bresp_i(eth_axi_bresp),
        .axi_bvalid_i(eth_axi_bvalid),
        .axi_bready_o(eth_axi_bready),
        .axi_awid_o(eth_axi_awid),
        .axi_awlen_o(eth_axi_awlen),
        .axi_awsize_o(eth_axi_awsize),
        .axi_awburst_o(eth_axi_awburst),
        .axi_awlock_o(eth_axi_awlock),
        .axi_awcache_o(eth_axi_awcache),
        .axi_awqos_o(eth_axi_awqos),
        .axi_wlast_o(eth_axi_wlast),
        .axi_bid_i(eth_axi_bid),
        // inta_o port: Interrupt Output A
        .inta_o(eth_interrupt),
        .phy_rstn_o(phy_rstn),
        // mii_io port: MII interface
        .mii_tx_clk_i(mii_tx_clk),
        .mii_txd_o(mii_rxd),
        .mii_tx_en_o(mii_rx_dv),
        .mii_tx_er_o(mii_rx_er),
        .mii_rx_clk_i(mii_rx_clk),
        .mii_rxd_i(mii_txd),
        .mii_rx_dv_i(mii_tx_en),
        .mii_rx_er_i(mii_tx_er),
        .mii_crs_i(mii_crs),
        .mii_col_i(mii_col),
        .mii_mdio_io(tb_mii_mdio),
        .mii_mdc_o(tb_mii_mdc)
        );

    
endmodule
