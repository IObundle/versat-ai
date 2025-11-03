`timescale 1ns / 1ps

module Relu 
   (
   //control
   input clk,
   input rst,

   input running,

   input [31:0] in0,

   (* versat_latency = 1 *) output reg [31:0] out0
   );

wire sign = in0[31];

always @(posedge clk,posedge rst) begin
   if(rst) begin
      out0 <= 0;
   end else if(running) begin
      out0 <= sign ? 32'h0 : in0;
   end
end

endmodule
