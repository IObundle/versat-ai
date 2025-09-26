`timescale 1ns / 1ps

/* verilator lint_off WIDTH */

module F_AccumMax #(
   parameter DATA_W = 32,
   parameter STRIDE_W = 16,
   parameter DELAY_W = 7
) (
   //control
   input clk,
   input rst,

   input run,
   input running,

   input [STRIDE_W-1:0] strideMinusOne,

   input [DATA_W-1:0] in0,

   (* versat_latency = 1 *) output [31:0] out0,

   input [DELAY_W-1:0] delay0
);

reg [DELAY_W-1:0] delay;

always @(posedge clk, posedge rst) begin
   if (rst) begin
      delay <= 0;
   end else if (run) begin
      delay <= delay0;
   end else if (|delay) begin
      delay <= delay - 1;
   end else begin
      delay <= strideMinusOne;
   end
end

wire store = (delay == 0);

reg [31:0] stored;

wire [DATA_W-1:0] bigger  = (in0[DATA_W-1] ^ stored[DATA_W-1])? (in0[DATA_W-1]? stored: in0):
                                 in0[DATA_W-1]? ((in0[DATA_W-2:0] > stored[DATA_W-2:0])? stored: in0):
                                 ((in0[DATA_W-2:0] > stored[DATA_W-2:0])? in0: stored);

always @(posedge clk,posedge rst) begin
   if(rst) begin
      stored <= 0;
   end else if(running) begin
      if(store) begin
         stored <= in0;
      end else begin
         stored <= bigger;
      end
   end
end

assign out0 = stored;

endmodule