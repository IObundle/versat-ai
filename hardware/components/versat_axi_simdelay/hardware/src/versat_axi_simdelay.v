`timescale 1ns / 1ps

module versat_axi_simdelay #(
      parameter AXI_ADDR_W = 32,
      parameter AXI_DATA_W = 32,
      parameter AXI_LEN_W  = 8,
      parameter AXI_ID_W   = 4
   ) (
   output [      AXI_ID_W-1:0] m_axi_awid_o,
   output [    AXI_ADDR_W-1:0] m_axi_awaddr_o,
   output [     AXI_LEN_W-1:0] m_axi_awlen_o,
   output [             3-1:0] m_axi_awsize_o,
   output [             2-1:0] m_axi_awburst_o,
   output [             2-1:0] m_axi_awlock_o,
   output [             4-1:0] m_axi_awcache_o,
   output [             3-1:0] m_axi_awprot_o,
   output [             4-1:0] m_axi_awqos_o,
   output [             1-1:0] m_axi_awvalid_o,
   input  [             1-1:0] m_axi_awready_i,

   output [    AXI_DATA_W-1:0] m_axi_wdata_o,
   output [(AXI_DATA_W/8)-1:0] m_axi_wstrb_o,
   output [             1-1:0] m_axi_wlast_o,
   output [             1-1:0] m_axi_wvalid_o,
   input  [             1-1:0] m_axi_wready_i,

   input  [      AXI_ID_W-1:0] m_axi_bid_i,
   input  [             2-1:0] m_axi_bresp_i,
   input  [             1-1:0] m_axi_bvalid_i,
   output [             1-1:0] m_axi_bready_o,

   output [      AXI_ID_W-1:0] m_axi_arid_o,
   output [    AXI_ADDR_W-1:0] m_axi_araddr_o,
   output [     AXI_LEN_W-1:0] m_axi_arlen_o,
   output [             3-1:0] m_axi_arsize_o,
   output [             2-1:0] m_axi_arburst_o,
   output [             2-1:0] m_axi_arlock_o,
   output [             4-1:0] m_axi_arcache_o,
   output [             3-1:0] m_axi_arprot_o,
   output [             4-1:0] m_axi_arqos_o,
   output [             1-1:0] m_axi_arvalid_o,
   input  [             1-1:0] m_axi_arready_i,

   input  [      AXI_ID_W-1:0] m_axi_rid_i,
   input  [    AXI_DATA_W-1:0] m_axi_rdata_i,
   input  [             2-1:0] m_axi_rresp_i,
   input  [             1-1:0] m_axi_rlast_i,
   input  [             1-1:0] m_axi_rvalid_i,
   output [             1-1:0] m_axi_rready_o,

//   

   input [      AXI_ID_W-1:0] s_axi_awid_i,
   input [    AXI_ADDR_W-1:0] s_axi_awaddr_i,
   input [     AXI_LEN_W-1:0] s_axi_awlen_i,
   input [             3-1:0] s_axi_awsize_i,
   input [             2-1:0] s_axi_awburst_i,
   input [             2-1:0] s_axi_awlock_i,
   input [             4-1:0] s_axi_awcache_i,
   input [             3-1:0] s_axi_awprot_i,
   input [             4-1:0] s_axi_awqos_i,
   input [             1-1:0] s_axi_awvalid_i,
   output  [           1-1:0] s_axi_awready_o,

   input [    AXI_DATA_W-1:0] s_axi_wdata_i,
   input [(AXI_DATA_W/8)-1:0] s_axi_wstrb_i,
   input [             1-1:0] s_axi_wlast_i,
   input [             1-1:0] s_axi_wvalid_i,
   output  [           1-1:0] s_axi_wready_o,

   output  [    AXI_ID_W-1:0] s_axi_bid_o,
   output  [           2-1:0] s_axi_bresp_o,
   output  [           1-1:0] s_axi_bvalid_o,
   input [             1-1:0] s_axi_bready_i,

   input [      AXI_ID_W-1:0] s_axi_arid_i,
   input [    AXI_ADDR_W-1:0] s_axi_araddr_i,
   input [     AXI_LEN_W-1:0] s_axi_arlen_i,
   input [             3-1:0] s_axi_arsize_i,
   input [             2-1:0] s_axi_arburst_i,
   input [             2-1:0] s_axi_arlock_i,
   input [             4-1:0] s_axi_arcache_i,
   input [             3-1:0] s_axi_arprot_i,
   input [             4-1:0] s_axi_arqos_i,
   input [             1-1:0] s_axi_arvalid_i,
   output  [           1-1:0] s_axi_arready_o,

   output  [    AXI_ID_W-1:0] s_axi_rid_o,
   output  [  AXI_DATA_W-1:0] s_axi_rdata_o,
   output  [           2-1:0] s_axi_rresp_o,
   output  [           1-1:0] s_axi_rlast_o,
   output  [           1-1:0] s_axi_rvalid_o,
   input [             1-1:0] s_axi_rready_i,

   input cke_i,
   input clk_i,
   input arst_i,
   input rst_i
   );

assign m_axi_awid_o = s_axi_awid_i;
assign m_axi_awaddr_o = s_axi_awaddr_i;
assign m_axi_awlen_o = s_axi_awlen_i;
assign m_axi_awsize_o = s_axi_awsize_i;
assign m_axi_awburst_o = s_axi_awburst_i;
assign m_axi_awlock_o = s_axi_awlock_i;
assign m_axi_awcache_o = s_axi_awcache_i;
assign m_axi_awprot_o = s_axi_awprot_i;
assign m_axi_awqos_o = s_axi_awqos_i;
assign m_axi_wdata_o = s_axi_wdata_i;
assign m_axi_wstrb_o = s_axi_wstrb_i;
assign m_axi_wlast_o = s_axi_wlast_i;
assign s_axi_bid_o = m_axi_bid_i;
assign s_axi_bresp_o = m_axi_bresp_i;
assign m_axi_arid_o = s_axi_arid_i;
assign m_axi_araddr_o = s_axi_araddr_i;
assign m_axi_arlen_o = s_axi_arlen_i;
assign m_axi_arsize_o = s_axi_arsize_i;
assign m_axi_arburst_o = s_axi_arburst_i;
assign m_axi_arlock_o = s_axi_arlock_i;
assign m_axi_arcache_o = s_axi_arcache_i;
assign m_axi_arprot_o = s_axi_arprot_i;
assign m_axi_arqos_o = s_axi_arqos_i;
assign s_axi_rid_o = m_axi_rid_i;
assign s_axi_rdata_o = m_axi_rdata_i;
assign s_axi_rresp_o = m_axi_rresp_i;
assign s_axi_rlast_o = m_axi_rlast_i;

VersatAxiDelay delayAW(
   .s_valid_i(s_axi_awvalid_i),
   .s_ready_o(s_axi_awready_o),
   .m_valid_o(m_axi_awvalid_o),
   .m_ready_i(m_axi_awready_i),
   .clk_i    (clk_i),
   .rst_i    (rst_i | arst_i)
);

VersatAxiDelay delayW(
   .s_valid_i(s_axi_wvalid_i),
   .s_ready_o(s_axi_wready_o),
   .m_valid_o(m_axi_wvalid_o),
   .m_ready_i(m_axi_wready_i),
   .clk_i    (clk_i),
   .rst_i    (rst_i | arst_i)
);

VersatAxiDelay delayB(
   .s_valid_i(m_axi_bvalid_i),
   .s_ready_o(m_axi_bready_o),
   .m_valid_o(s_axi_bvalid_o),
   .m_ready_i(s_axi_bready_i),
   .clk_i    (clk_i),
   .rst_i    (rst_i | arst_i)
);

VersatAxiDelay delayAR(
   .s_valid_i(s_axi_arvalid_i),
   .s_ready_o(s_axi_arready_o),
   .m_valid_o(m_axi_arvalid_o),
   .m_ready_i(m_axi_arready_i),
   .clk_i    (clk_i),
   .rst_i    (rst_i | arst_i)
);

VersatAxiDelay delayR(
   .s_valid_i(m_axi_rvalid_i),
   .s_ready_o(m_axi_rready_o),
   .m_valid_o(s_axi_rvalid_o),
   .m_ready_i(s_axi_rready_i),
   .clk_i    (clk_i),
   .rst_i    (rst_i | arst_i)
);

endmodule
