`timescale 1ns / 1ps

module fp_special #(
                    parameter DATA_W = 32,
                    parameter EXP_W = 8
                    )
   (
    input [DATA_W-2:0] data_i,

    output             nan,
    output             infinite,
    output             zero
    );

   localparam MAN_W = DATA_W-EXP_W;

   wire [EXP_W-1:0]    exponent = data_i[DATA_W-2 -: EXP_W];
   wire [MAN_W-2:0]    mantissa = data_i[MAN_W-2:0];

   wire                exp_all_ones = &exponent;
   wire                exp_zero = ~|exponent;
   wire                man_nzero = |mantissa;
   wire                man_zero = ~man_nzero;

   assign nan       = exp_all_ones & man_nzero;
   assign infinite  = exp_all_ones & man_zero;
   assign zero      = exp_zero & man_zero;

endmodule
