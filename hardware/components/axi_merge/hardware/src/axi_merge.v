/*

Copyright (c) 2020 Alex Forencich

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
// Linebreak
`timescale 1ns / 1ps
// Linebreak
`default_nettype none

/*
 * AXI4 2x1 merge (wrapper)
 */
module axi_merge #
(
    parameter DATA_WIDTH = 32,
    parameter ADDR_WIDTH = 32,
    parameter STRB_WIDTH = (DATA_WIDTH/8),
    parameter ID_WIDTH = 8,
    parameter AWUSER_ENABLE = 0,
    parameter AWUSER_WIDTH = 1,
    parameter WUSER_ENABLE = 0,
    parameter WUSER_WIDTH = 1,
    parameter BUSER_ENABLE = 0,
    parameter BUSER_WIDTH = 1,
    parameter ARUSER_ENABLE = 0,
    parameter ARUSER_WIDTH = 1,
    parameter RUSER_ENABLE = 0,
    parameter RUSER_WIDTH = 1,
    parameter FORWARD_ID = 0,
    parameter M_REGIONS = 1,
    parameter M00_BASE_ADDR = 0,
    parameter M00_ADDR_WIDTH = {M_REGIONS{32'd32}},
    parameter M00_CONNECT_READ = 2'b11,
    parameter M00_CONNECT_WRITE = 2'b11,
    parameter M00_SECURE = 1'b0
)
(
    input wire cke_i,
    input wire clk_i,
    input wire arst_i,
    input wire rst_i,

    /*
     * AXI slave interface
     */
    input  wire [ID_WIDTH-1:0]      s00_axi_awid_i,
    input  wire [ADDR_WIDTH-1:0]    s00_axi_awaddr_i,
    input  wire [7:0]               s00_axi_awlen_i,
    input  wire [2:0]               s00_axi_awsize_i,
    input  wire [1:0]               s00_axi_awburst_i,
    input  wire                     s00_axi_awlock_i,
    input  wire [3:0]               s00_axi_awcache_i,
    input  wire [2:0]               s00_axi_awprot_i,
    input  wire [3:0]               s00_axi_awqos_i,
    input  wire [AWUSER_WIDTH-1:0]  s00_axi_awuser_i,
    input  wire                     s00_axi_awvalid_i,
    output wire                     s00_axi_awready_o,
    input  wire [DATA_WIDTH-1:0]    s00_axi_wdata_i,
    input  wire [STRB_WIDTH-1:0]    s00_axi_wstrb_i,
    input  wire                     s00_axi_wlast_i,
    input  wire [WUSER_WIDTH-1:0]   s00_axi_wuser_i,
    input  wire                     s00_axi_wvalid_i,
    output wire                     s00_axi_wready_o,
    output wire [ID_WIDTH-1:0]      s00_axi_bid_o,
    output wire [1:0]               s00_axi_bresp_o,
    output wire [BUSER_WIDTH-1:0]   s00_axi_buser_o,
    output wire                     s00_axi_bvalid_o,
    input  wire                     s00_axi_bready_i,
    input  wire [ID_WIDTH-1:0]      s00_axi_arid_i,
    input  wire [ADDR_WIDTH-1:0]    s00_axi_araddr_i,
    input  wire [7:0]               s00_axi_arlen_i,
    input  wire [2:0]               s00_axi_arsize_i,
    input  wire [1:0]               s00_axi_arburst_i,
    input  wire                     s00_axi_arlock_i,
    input  wire [3:0]               s00_axi_arcache_i,
    input  wire [2:0]               s00_axi_arprot_i,
    input  wire [3:0]               s00_axi_arqos_i,
    input  wire [ARUSER_WIDTH-1:0]  s00_axi_aruser_i,
    input  wire                     s00_axi_arvalid_i,
    output wire                     s00_axi_arready_o,
    output wire [ID_WIDTH-1:0]      s00_axi_rid_o,
    output wire [DATA_WIDTH-1:0]    s00_axi_rdata_o,
    output wire [1:0]               s00_axi_rresp_o,
    output wire                     s00_axi_rlast_o,
    output wire [RUSER_WIDTH-1:0]   s00_axi_ruser_o,
    output wire                     s00_axi_rvalid_o,
    input  wire                     s00_axi_rready_i,

    input  wire [ID_WIDTH-1:0]      s01_axi_awid_i,
    input  wire [ADDR_WIDTH-1:0]    s01_axi_awaddr_i,
    input  wire [7:0]               s01_axi_awlen_i,
    input  wire [2:0]               s01_axi_awsize_i,
    input  wire [1:0]               s01_axi_awburst_i,
    input  wire                     s01_axi_awlock_i,
    input  wire [3:0]               s01_axi_awcache_i,
    input  wire [2:0]               s01_axi_awprot_i,
    input  wire [3:0]               s01_axi_awqos_i,
    input  wire [AWUSER_WIDTH-1:0]  s01_axi_awuser_i,
    input  wire                     s01_axi_awvalid_i,
    output wire                     s01_axi_awready_o,
    input  wire [DATA_WIDTH-1:0]    s01_axi_wdata_i,
    input  wire [STRB_WIDTH-1:0]    s01_axi_wstrb_i,
    input  wire                     s01_axi_wlast_i,
    input  wire [WUSER_WIDTH-1:0]   s01_axi_wuser_i,
    input  wire                     s01_axi_wvalid_i,
    output wire                     s01_axi_wready_o,
    output wire [ID_WIDTH-1:0]      s01_axi_bid_o,
    output wire [1:0]               s01_axi_bresp_o,
    output wire [BUSER_WIDTH-1:0]   s01_axi_buser_o,
    output wire                     s01_axi_bvalid_o,
    input  wire                     s01_axi_bready_i,
    input  wire [ID_WIDTH-1:0]      s01_axi_arid_i,
    input  wire [ADDR_WIDTH-1:0]    s01_axi_araddr_i,
    input  wire [7:0]               s01_axi_arlen_i,
    input  wire [2:0]               s01_axi_arsize_i,
    input  wire [1:0]               s01_axi_arburst_i,
    input  wire                     s01_axi_arlock_i,
    input  wire [3:0]               s01_axi_arcache_i,
    input  wire [2:0]               s01_axi_arprot_i,
    input  wire [3:0]               s01_axi_arqos_i,
    input  wire [ARUSER_WIDTH-1:0]  s01_axi_aruser_i,
    input  wire                     s01_axi_arvalid_i,
    output wire                     s01_axi_arready_o,
    output wire [ID_WIDTH-1:0]      s01_axi_rid_o,
    output wire [DATA_WIDTH-1:0]    s01_axi_rdata_o,
    output wire [1:0]               s01_axi_rresp_o,
    output wire                     s01_axi_rlast_o,
    output wire [RUSER_WIDTH-1:0]   s01_axi_ruser_o,
    output wire                     s01_axi_rvalid_o,
    input  wire                     s01_axi_rready_i,

    /*
     * AXI master interface
     */
    output wire [ID_WIDTH-1:0]      m00_axi_awid_o,
    output wire [ADDR_WIDTH-1:0]    m00_axi_awaddr_o,
    output wire [7:0]               m00_axi_awlen_o,
    output wire [2:0]               m00_axi_awsize_o,
    output wire [1:0]               m00_axi_awburst_o,
    output wire                     m00_axi_awlock_o,
    output wire [3:0]               m00_axi_awcache_o,
    output wire [2:0]               m00_axi_awprot_o,
    output wire [3:0]               m00_axi_awqos_o,
    output wire [3:0]               m00_axi_awregion_o,
    output wire [AWUSER_WIDTH-1:0]  m00_axi_awuser_o,
    output wire                     m00_axi_awvalid_o,
    input  wire                     m00_axi_awready_i,
    output wire [DATA_WIDTH-1:0]    m00_axi_wdata_o,
    output wire [STRB_WIDTH-1:0]    m00_axi_wstrb_o,
    output wire                     m00_axi_wlast_o,
    output wire [WUSER_WIDTH-1:0]   m00_axi_wuser_o,
    output wire                     m00_axi_wvalid_o,
    input  wire                     m00_axi_wready_i,
    input  wire [ID_WIDTH-1:0]      m00_axi_bid_i,
    input  wire [1:0]               m00_axi_bresp_i,
    input  wire [BUSER_WIDTH-1:0]   m00_axi_buser_i,
    input  wire                     m00_axi_bvalid_i,
    output wire                     m00_axi_bready_o,
    output wire [ID_WIDTH-1:0]      m00_axi_arid_o,
    output wire [ADDR_WIDTH-1:0]    m00_axi_araddr_o,
    output wire [7:0]               m00_axi_arlen_o,
    output wire [2:0]               m00_axi_arsize_o,
    output wire [1:0]               m00_axi_arburst_o,
    output wire                     m00_axi_arlock_o,
    output wire [3:0]               m00_axi_arcache_o,
    output wire [2:0]               m00_axi_arprot_o,
    output wire [3:0]               m00_axi_arqos_o,
    output wire [3:0]               m00_axi_arregion_o,
    output wire [ARUSER_WIDTH-1:0]  m00_axi_aruser_o,
    output wire                     m00_axi_arvalid_o,
    input  wire                     m00_axi_arready_i,
    input  wire [ID_WIDTH-1:0]      m00_axi_rid_i,
    input  wire [DATA_WIDTH-1:0]    m00_axi_rdata_i,
    input  wire [1:0]               m00_axi_rresp_i,
    input  wire                     m00_axi_rlast_i,
    input  wire [RUSER_WIDTH-1:0]   m00_axi_ruser_i,
    input  wire                     m00_axi_rvalid_i,
    output wire                     m00_axi_rready_o
);

localparam S_COUNT = 2;
localparam M_COUNT = 1;

// parameter sizing helpers
function [ADDR_WIDTH*M_REGIONS-1:0] w_a_r(input [ADDR_WIDTH*M_REGIONS-1:0] val);
    w_a_r = val;
endfunction

function [32*M_REGIONS-1:0] w_32_r(input [32*M_REGIONS-1:0] val);
    w_32_r = val;
endfunction

function [S_COUNT-1:0] w_s(input [S_COUNT-1:0] val);
    w_s = val;
endfunction

function w_1(input val);
    w_1 = val;
endfunction

axi_interconnect #(
    .S_COUNT(S_COUNT),
    .M_COUNT(M_COUNT),
    .DATA_WIDTH(DATA_WIDTH),
    .ADDR_WIDTH(ADDR_WIDTH),
    .STRB_WIDTH(STRB_WIDTH),
    .ID_WIDTH(ID_WIDTH),
    .AWUSER_ENABLE(AWUSER_ENABLE),
    .AWUSER_WIDTH(AWUSER_WIDTH),
    .WUSER_ENABLE(WUSER_ENABLE),
    .WUSER_WIDTH(WUSER_WIDTH),
    .BUSER_ENABLE(BUSER_ENABLE),
    .BUSER_WIDTH(BUSER_WIDTH),
    .ARUSER_ENABLE(ARUSER_ENABLE),
    .ARUSER_WIDTH(ARUSER_WIDTH),
    .RUSER_ENABLE(RUSER_ENABLE),
    .RUSER_WIDTH(RUSER_WIDTH),
    .FORWARD_ID(FORWARD_ID),
    .M_REGIONS(M_REGIONS),
    .M_BASE_ADDR(w_a_r(M00_BASE_ADDR)),
    .M_ADDR_WIDTH(w_32_r(M00_ADDR_WIDTH)),
    .M_CONNECT_READ(w_s(M00_CONNECT_READ)),
    .M_CONNECT_WRITE(w_s(M00_CONNECT_WRITE)),
    .M_SECURE(w_1(M00_SECURE))
)
axi_interconnect_inst (
    .clk(clk_i),
    .rst(rst_i | arst_i),
    .s_axi_awid({ s01_axi_awid_i, s00_axi_awid_i }),
    .s_axi_awaddr({ s01_axi_awaddr_i, s00_axi_awaddr_i }),
    .s_axi_awlen({ s01_axi_awlen_i, s00_axi_awlen_i }),
    .s_axi_awsize({ s01_axi_awsize_i, s00_axi_awsize_i }),
    .s_axi_awburst({ s01_axi_awburst_i, s00_axi_awburst_i }),
    .s_axi_awlock({ s01_axi_awlock_i, s00_axi_awlock_i }),
    .s_axi_awcache({ s01_axi_awcache_i, s00_axi_awcache_i }),
    .s_axi_awprot({ s01_axi_awprot_i, s00_axi_awprot_i }),
    .s_axi_awqos({ s01_axi_awqos_i, s00_axi_awqos_i }),
    .s_axi_awuser({ s01_axi_awuser_i, s00_axi_awuser_i }),
    .s_axi_awvalid({ s01_axi_awvalid_i, s00_axi_awvalid_i }),
    .s_axi_awready({ s01_axi_awready_o, s00_axi_awready_o }),
    .s_axi_wdata({ s01_axi_wdata_i, s00_axi_wdata_i }),
    .s_axi_wstrb({ s01_axi_wstrb_i, s00_axi_wstrb_i }),
    .s_axi_wlast({ s01_axi_wlast_i, s00_axi_wlast_i }),
    .s_axi_wuser({ s01_axi_wuser_i, s00_axi_wuser_i }),
    .s_axi_wvalid({ s01_axi_wvalid_i, s00_axi_wvalid_i }),
    .s_axi_wready({ s01_axi_wready_o, s00_axi_wready_o }),
    .s_axi_bid({ s01_axi_bid_o, s00_axi_bid_o }),
    .s_axi_bresp({ s01_axi_bresp_o, s00_axi_bresp_o }),
    .s_axi_buser({ s01_axi_buser_o, s00_axi_buser_o }),
    .s_axi_bvalid({ s01_axi_bvalid_o, s00_axi_bvalid_o }),
    .s_axi_bready({ s01_axi_bready_i, s00_axi_bready_i }),
    .s_axi_arid({ s01_axi_arid_i, s00_axi_arid_i }),
    .s_axi_araddr({ s01_axi_araddr_i, s00_axi_araddr_i }),
    .s_axi_arlen({ s01_axi_arlen_i, s00_axi_arlen_i }),
    .s_axi_arsize({ s01_axi_arsize_i, s00_axi_arsize_i }),
    .s_axi_arburst({ s01_axi_arburst_i, s00_axi_arburst_i }),
    .s_axi_arlock({ s01_axi_arlock_i, s00_axi_arlock_i }),
    .s_axi_arcache({ s01_axi_arcache_i, s00_axi_arcache_i }),
    .s_axi_arprot({ s01_axi_arprot_i, s00_axi_arprot_i }),
    .s_axi_arqos({ s01_axi_arqos_i, s00_axi_arqos_i }),
    .s_axi_aruser({ s01_axi_aruser_i, s00_axi_aruser_i }),
    .s_axi_arvalid({ s01_axi_arvalid_i, s00_axi_arvalid_i }),
    .s_axi_arready({ s01_axi_arready_o, s00_axi_arready_o }),
    .s_axi_rid({ s01_axi_rid_o, s00_axi_rid_o }),
    .s_axi_rdata({ s01_axi_rdata_o, s00_axi_rdata_o }),
    .s_axi_rresp({ s01_axi_rresp_o, s00_axi_rresp_o }),
    .s_axi_rlast({ s01_axi_rlast_o, s00_axi_rlast_o }),
    .s_axi_ruser({ s01_axi_ruser_o, s00_axi_ruser_o }),
    .s_axi_rvalid({ s01_axi_rvalid_o, s00_axi_rvalid_o }),
    .s_axi_rready({ s01_axi_rready_i, s00_axi_rready_i }),
    .m_axi_awid(m00_axi_awid_o),
    .m_axi_awaddr(m00_axi_awaddr_o),
    .m_axi_awlen(m00_axi_awlen_o),
    .m_axi_awsize(m00_axi_awsize_o),
    .m_axi_awburst(m00_axi_awburst_o),
    .m_axi_awlock(m00_axi_awlock_o),
    .m_axi_awcache(m00_axi_awcache_o),
    .m_axi_awprot(m00_axi_awprot_o),
    .m_axi_awqos(m00_axi_awqos_o),
    .m_axi_awregion(m00_axi_awregion_o),
    .m_axi_awuser(m00_axi_awuser_o),
    .m_axi_awvalid(m00_axi_awvalid_o),
    .m_axi_awready(m00_axi_awready_i),
    .m_axi_wdata(m00_axi_wdata_o),
    .m_axi_wstrb(m00_axi_wstrb_o),
    .m_axi_wlast(m00_axi_wlast_o),
    .m_axi_wuser(m00_axi_wuser_o),
    .m_axi_wvalid(m00_axi_wvalid_o),
    .m_axi_wready(m00_axi_wready_i),
    .m_axi_bid(m00_axi_bid_i),
    .m_axi_bresp(m00_axi_bresp_i),
    .m_axi_buser(m00_axi_buser_i),
    .m_axi_bvalid(m00_axi_bvalid_i),
    .m_axi_bready(m00_axi_bready_o),
    .m_axi_arid(m00_axi_arid_o),
    .m_axi_araddr(m00_axi_araddr_o),
    .m_axi_arlen(m00_axi_arlen_o),
    .m_axi_arsize(m00_axi_arsize_o),
    .m_axi_arburst(m00_axi_arburst_o),
    .m_axi_arlock(m00_axi_arlock_o),
    .m_axi_arcache(m00_axi_arcache_o),
    .m_axi_arprot(m00_axi_arprot_o),
    .m_axi_arqos(m00_axi_arqos_o),
    .m_axi_arregion(m00_axi_arregion_o),
    .m_axi_aruser(m00_axi_aruser_o),
    .m_axi_arvalid(m00_axi_arvalid_o),
    .m_axi_arready(m00_axi_arready_i),
    .m_axi_rid(m00_axi_rid_i),
    .m_axi_rdata(m00_axi_rdata_i),
    .m_axi_rresp(m00_axi_rresp_i),
    .m_axi_rlast(m00_axi_rlast_i),
    .m_axi_ruser(m00_axi_ruser_i),
    .m_axi_rvalid(m00_axi_rvalid_i),
    .m_axi_rready(m00_axi_rready_o)
);

endmodule

`resetall
