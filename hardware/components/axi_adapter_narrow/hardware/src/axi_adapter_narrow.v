/*

Copyright (c) 2018 Alex Forencich

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

*/

// Language: Verilog 2001

`resetall
// Test1
`timescale 1ns / 1ps
// Test1
`default_nettype none

/*
 * AXI4 width adapter
 */
module axi_adapter_narrow #
(
    // Width of address bus in bits
    parameter ADDR_WIDTH = 32,
    // Width of input (slave) interface data bus in bits
    parameter S_DATA_WIDTH = 32,
    // Width of input (slave) interface wstrb (width of data bus in words)
    parameter S_STRB_WIDTH = (S_DATA_WIDTH/8),
    // Width of output (master) interface data bus in bits
    parameter M_DATA_WIDTH = 32,
    // Width of output (master) interface wstrb (width of data bus in words)
    parameter M_STRB_WIDTH = (M_DATA_WIDTH/8),
    // Width of ID signal
    parameter ID_WIDTH = 8,
    // Propagate awuser signal
    parameter AWUSER_ENABLE = 0,
    // Width of awuser signal
    parameter AWUSER_WIDTH = 1,
    // Propagate wuser signal
    parameter WUSER_ENABLE = 0,
    // Width of wuser signal
    parameter WUSER_WIDTH = 1,
    // Propagate buser signal
    parameter BUSER_ENABLE = 0,
    // Width of buser signal
    parameter BUSER_WIDTH = 1,
    // Propagate aruser signal
    parameter ARUSER_ENABLE = 0,
    // Width of aruser signal
    parameter ARUSER_WIDTH = 1,
    // Propagate ruser signal
    parameter RUSER_ENABLE = 0,
    // Width of ruser signal
    parameter RUSER_WIDTH = 1,
    // When adapting to a wider bus, re-pack full-width burst instead of passing through narrow burst if possible
    parameter CONVERT_BURST = 1,
    // When adapting to a wider bus, re-pack all bursts instead of passing through narrow burst if possible
    parameter CONVERT_NARROW_BURST = 1,
    // Forward ID through adapter
    parameter FORWARD_ID = 0
)
(
    input wire cke_i,
    input wire clk_i,
    input wire arst_i,

    /*
     * AXI slave interface
     */
    input  wire [ID_WIDTH-1:0]      s_axi_awid_i,
    input  wire [ADDR_WIDTH-1:0]    s_axi_awaddr_i,
    input  wire [7:0]               s_axi_awlen_i,
    input  wire [2:0]               s_axi_awsize_i,
    input  wire [1:0]               s_axi_awburst_i,
    input  wire                     s_axi_awlock_i,
    input  wire [3:0]               s_axi_awcache_i,
    input  wire [2:0]               s_axi_awprot_i,
    input  wire [3:0]               s_axi_awqos_i,
    input  wire [3:0]               s_axi_awregion_i,
    input  wire [AWUSER_WIDTH-1:0]  s_axi_awuser_i,
    input  wire                     s_axi_awvalid_i,
    output wire                     s_axi_awready_o,
    input  wire [S_DATA_WIDTH-1:0]  s_axi_wdata_i,
    input  wire [S_STRB_WIDTH-1:0]  s_axi_wstrb_i,
    input  wire                     s_axi_wlast_i,
    input  wire [WUSER_WIDTH-1:0]   s_axi_wuser_i,
    input  wire                     s_axi_wvalid_i,
    output wire                     s_axi_wready_o,
    output wire [ID_WIDTH-1:0]      s_axi_bid_o,
    output wire [1:0]               s_axi_bresp_o,
    output wire [BUSER_WIDTH-1:0]   s_axi_buser_o,
    output wire                     s_axi_bvalid_o,
    input  wire                     s_axi_bready_i,
    input  wire [ID_WIDTH-1:0]      s_axi_arid_i,
    input  wire [ADDR_WIDTH-1:0]    s_axi_araddr_i,
    input  wire [7:0]               s_axi_arlen_i,
    input  wire [2:0]               s_axi_arsize_i,
    input  wire [1:0]               s_axi_arburst_i,
    input  wire                     s_axi_arlock_i,
    input  wire [3:0]               s_axi_arcache_i,
    input  wire [2:0]               s_axi_arprot_i,
    input  wire [3:0]               s_axi_arqos_i,
    input  wire [3:0]               s_axi_arregion_i,
    input  wire [ARUSER_WIDTH-1:0]  s_axi_aruser_i,
    input  wire                     s_axi_arvalid_i,
    output wire                     s_axi_arready_o,
    output wire [ID_WIDTH-1:0]      s_axi_rid_o,
    output wire [S_DATA_WIDTH-1:0]  s_axi_rdata_o,
    output wire [1:0]               s_axi_rresp_o,
    output wire                     s_axi_rlast_o,
    output wire [RUSER_WIDTH-1:0]   s_axi_ruser_o,
    output wire                     s_axi_rvalid_o,
    input  wire                     s_axi_rready_i,

    /*
     * AXI master interface
     */
    output wire [ID_WIDTH-1:0]      m_axi_awid_o,
    output wire [ADDR_WIDTH-1:0]    m_axi_awaddr_o,
    output wire [7:0]               m_axi_awlen_o,
    output wire [2:0]               m_axi_awsize_o,
    output wire [1:0]               m_axi_awburst_o,
    output wire                     m_axi_awlock_o,
    output wire [3:0]               m_axi_awcache_o,
    output wire [2:0]               m_axi_awprot_o,
    output wire [3:0]               m_axi_awqos_o,
    output wire [3:0]               m_axi_awregion_o,
    output wire [AWUSER_WIDTH-1:0]  m_axi_awuser_o,
    output wire                     m_axi_awvalid_o,
    input  wire                     m_axi_awready_i,
    output wire [M_DATA_WIDTH-1:0]  m_axi_wdata_o,
    output wire [M_STRB_WIDTH-1:0]  m_axi_wstrb_o,
    output wire                     m_axi_wlast_o,
    output wire [WUSER_WIDTH-1:0]   m_axi_wuser_o,
    output wire                     m_axi_wvalid_o,
    input  wire                     m_axi_wready_i,
    input  wire [ID_WIDTH-1:0]      m_axi_bid_i,
    input  wire [1:0]               m_axi_bresp_i,
    input  wire [BUSER_WIDTH-1:0]   m_axi_buser_i,
    input  wire                     m_axi_bvalid_i,
    output wire                     m_axi_bready_o,
    output wire [ID_WIDTH-1:0]      m_axi_arid_o,
    output wire [ADDR_WIDTH-1:0]    m_axi_araddr_o,
    output wire [7:0]               m_axi_arlen_o,
    output wire [2:0]               m_axi_arsize_o,
    output wire [1:0]               m_axi_arburst_o,
    output wire                     m_axi_arlock_o,
    output wire [3:0]               m_axi_arcache_o,
    output wire [2:0]               m_axi_arprot_o,
    output wire [3:0]               m_axi_arqos_o,
    output wire [3:0]               m_axi_arregion_o,
    output wire [ARUSER_WIDTH-1:0]  m_axi_aruser_o,
    output wire                     m_axi_arvalid_o,
    input  wire                     m_axi_arready_i,
    input  wire [ID_WIDTH-1:0]      m_axi_rid_i,
    input  wire [M_DATA_WIDTH-1:0]  m_axi_rdata_i,
    input  wire [1:0]               m_axi_rresp_i,
    input  wire                     m_axi_rlast_i,
    input  wire [RUSER_WIDTH-1:0]   m_axi_ruser_i,
    input  wire                     m_axi_rvalid_i,
    output wire                     m_axi_rready_o
);

axi_adapter_wr_narrow #(
    .ADDR_WIDTH(ADDR_WIDTH),
    .S_DATA_WIDTH(S_DATA_WIDTH),
    .S_STRB_WIDTH(S_STRB_WIDTH),
    .M_DATA_WIDTH(M_DATA_WIDTH),
    .M_STRB_WIDTH(M_STRB_WIDTH),
    .ID_WIDTH(ID_WIDTH),
    .AWUSER_ENABLE(AWUSER_ENABLE),
    .AWUSER_WIDTH(AWUSER_WIDTH),
    .WUSER_ENABLE(WUSER_ENABLE),
    .WUSER_WIDTH(WUSER_WIDTH),
    .BUSER_ENABLE(BUSER_ENABLE),
    .BUSER_WIDTH(BUSER_WIDTH),
    .CONVERT_BURST(CONVERT_BURST),
    .CONVERT_NARROW_BURST(CONVERT_NARROW_BURST),
    .FORWARD_ID(FORWARD_ID)
)
axi_adapter_wr_inst (
    .clk(clk_i),
    .rst(arst_i),

    /*
     * AXI slave interface
     */
    .s_axi_awid(s_axi_awid_i),
    .s_axi_awaddr(s_axi_awaddr_i),
    .s_axi_awlen(s_axi_awlen_i),
    .s_axi_awsize(s_axi_awsize_i),
    .s_axi_awburst(s_axi_awburst_i),
    .s_axi_awlock(s_axi_awlock_i),
    .s_axi_awcache(s_axi_awcache_i),
    .s_axi_awprot(s_axi_awprot_i),
    .s_axi_awqos(s_axi_awqos_i),
    .s_axi_awregion(s_axi_awregion_i),
    .s_axi_awuser(s_axi_awuser_i),
    .s_axi_awvalid(s_axi_awvalid_i),
    .s_axi_awready(s_axi_awready_o),
    .s_axi_wdata(s_axi_wdata_i),
    .s_axi_wstrb(s_axi_wstrb_i),
    .s_axi_wlast(s_axi_wlast_i),
    .s_axi_wuser(s_axi_wuser_i),
    .s_axi_wvalid(s_axi_wvalid_i),
    .s_axi_wready(s_axi_wready_o),
    .s_axi_bid(s_axi_bid_o),
    .s_axi_bresp(s_axi_bresp_o),
    .s_axi_buser(s_axi_buser_o),
    .s_axi_bvalid(s_axi_bvalid_o),
    .s_axi_bready(s_axi_bready_i),

    /*
     * AXI master interface
     */
    .m_axi_awid(m_axi_awid_o),
    .m_axi_awaddr(m_axi_awaddr_o),
    .m_axi_awlen(m_axi_awlen_o),
    .m_axi_awsize(m_axi_awsize_o),
    .m_axi_awburst(m_axi_awburst_o),
    .m_axi_awlock(m_axi_awlock_o),
    .m_axi_awcache(m_axi_awcache_o),
    .m_axi_awprot(m_axi_awprot_o),
    .m_axi_awqos(m_axi_awqos_o),
    .m_axi_awregion(m_axi_awregion_o),
    .m_axi_awuser(m_axi_awuser_o),
    .m_axi_awvalid(m_axi_awvalid_o),
    .m_axi_awready(m_axi_awready_i),
    .m_axi_wdata(m_axi_wdata_o),
    .m_axi_wstrb(m_axi_wstrb_o),
    .m_axi_wlast(m_axi_wlast_o),
    .m_axi_wuser(m_axi_wuser_o),
    .m_axi_wvalid(m_axi_wvalid_o),
    .m_axi_wready(m_axi_wready_i),
    .m_axi_bid(m_axi_bid_i),
    .m_axi_bresp(m_axi_bresp_i),
    .m_axi_buser(m_axi_buser_i),
    .m_axi_bvalid(m_axi_bvalid_i),
    .m_axi_bready(m_axi_bready_o)
);

axi_adapter_rd_narrow #(
    .ADDR_WIDTH(ADDR_WIDTH),
    .S_DATA_WIDTH(S_DATA_WIDTH),
    .S_STRB_WIDTH(S_STRB_WIDTH),
    .M_DATA_WIDTH(M_DATA_WIDTH),
    .M_STRB_WIDTH(M_STRB_WIDTH),
    .ID_WIDTH(ID_WIDTH),
    .ARUSER_ENABLE(ARUSER_ENABLE),
    .ARUSER_WIDTH(ARUSER_WIDTH),
    .RUSER_ENABLE(RUSER_ENABLE),
    .RUSER_WIDTH(RUSER_WIDTH),
    .CONVERT_BURST(CONVERT_BURST),
    .CONVERT_NARROW_BURST(CONVERT_NARROW_BURST),
    .FORWARD_ID(FORWARD_ID)
)
axi_adapter_rd_inst (
    .clk(clk_i),
    .rst(arst_i),

    /*
     * AXI slave interface
     */
    .s_axi_arid(s_axi_arid_i),
    .s_axi_araddr(s_axi_araddr_i),
    .s_axi_arlen(s_axi_arlen_i),
    .s_axi_arsize(s_axi_arsize_i),
    .s_axi_arburst(s_axi_arburst_i),
    .s_axi_arlock(s_axi_arlock_i),
    .s_axi_arcache(s_axi_arcache_i),
    .s_axi_arprot(s_axi_arprot_i),
    .s_axi_arqos(s_axi_arqos_i),
    .s_axi_arregion(s_axi_arregion_i),
    .s_axi_aruser(s_axi_aruser_i),
    .s_axi_arvalid(s_axi_arvalid_i),
    .s_axi_arready(s_axi_arready_o),
    .s_axi_rid(s_axi_rid_o),
    .s_axi_rdata(s_axi_rdata_o),
    .s_axi_rresp(s_axi_rresp_o),
    .s_axi_rlast(s_axi_rlast_o),
    .s_axi_ruser(s_axi_ruser_o),
    .s_axi_rvalid(s_axi_rvalid_o),
    .s_axi_rready(s_axi_rready_i),

    /*
     * AXI master interface
     */
    .m_axi_arid(m_axi_arid_o),
    .m_axi_araddr(m_axi_araddr_o),
    .m_axi_arlen(m_axi_arlen_o),
    .m_axi_arsize(m_axi_arsize_o),
    .m_axi_arburst(m_axi_arburst_o),
    .m_axi_arlock(m_axi_arlock_o),
    .m_axi_arcache(m_axi_arcache_o),
    .m_axi_arprot(m_axi_arprot_o),
    .m_axi_arqos(m_axi_arqos_o),
    .m_axi_arregion(m_axi_arregion_o),
    .m_axi_aruser(m_axi_aruser_o),
    .m_axi_arvalid(m_axi_arvalid_o),
    .m_axi_arready(m_axi_arready_i),
    .m_axi_rid(m_axi_rid_i),
    .m_axi_rdata(m_axi_rdata_i),
    .m_axi_rresp(m_axi_rresp_i),
    .m_axi_rlast(m_axi_rlast_i),
    .m_axi_ruser(m_axi_ruser_i),
    .m_axi_rvalid(m_axi_rvalid_i),
    .m_axi_rready(m_axi_rready_o)
);

endmodule

`resetall
