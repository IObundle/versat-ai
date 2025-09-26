`timescale 1ns / 1ps

module clz #(
             parameter DATA_W = 279,
             parameter OUT_W = 9
             )
  (
   input [DATA_W-1:0]     data_i,
   output reg [OUT_W-1:0] data_o
   );

   localparam BIT_W = $clog2(DATA_W+1);

   integer                         i;

   always @* begin
      data_o = DATA_W[BIT_W-1:0];
      for (i=0; i < DATA_W; i=i+1) begin
         if (data_i[i]) begin
            data_o = (DATA_W[BIT_W-1:0] - i[BIT_W-1:0] - 1);
         end
      end
   end

endmodule
