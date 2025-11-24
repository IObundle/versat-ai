`timescale 1ns / 1ps

// Since Simple interface expects to write N transfers regardless of anything else (does not care about alignment or axi boundary)
// it becomes simpler to just have a module that performs N transfers from 
module TransferNFromSimpleM #(
   parameter AXI_DATA_W = 32,
   parameter MAX_TRANSF_W = 32
   ) (
      input [MAX_TRANSF_W-1:0] transferCount_i,
      input                    initiateTransfer_i,

      // NOTE: Because axi is divided into bursts (meaning that the transfer is paused temporarely)
      //       while this unit is always working after starting, that means that we need to
      //       make sure that the signals that are connected to axi are not "enabled" 
      //       unless we are in a state where the transfer is ocurring. Basically, while axi is not
      //       using the W channel, the inputs of this unit and the outputs basically need to be set
      //       to zero.

      // Connect directly to simple axi 
      input                        m_wvalid_i,
      output                       m_wready_o,
      input [      AXI_DATA_W-1:0] m_wdata_i,
      output                       m_wlast_o,

      // Data output
      output                  data_valid_o,
      output [AXI_DATA_W-1:0] data_o,
      input                   data_ready_i,

      input rst_i,
      input clk_i
   );

reg [MAX_TRANSF_W-1:0] count;
reg working;

assign m_wready_o = working && data_ready_i;
assign data_valid_o = working && m_wvalid_i;
assign data_o = m_wdata_i;

assign m_wlast_o = working && (count <= 1);

always @(posedge clk_i,posedge rst_i) begin
   if(rst_i) begin
      count <= 0;
      working <= 1'b0;
   end else if(working) begin
      if(m_wvalid_i && m_wready_o) begin
         count <= count - 1;

         if(m_wlast_o) begin
            working <= 1'b0;
         end
      end
   end else if(initiateTransfer_i) begin
      count <= transferCount_i;
      working <= 1'b1;
   end
end

endmodule

