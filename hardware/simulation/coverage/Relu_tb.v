`timescale 1ns / 1ps

// verilator coverage_off
module Relu_tb (

);
  localparam DATA_W = 32;
  // Inputs
  reg [(1)-1:0] clk_i;
  reg [(1)-1:0] rst_i;
  reg [(1)-1:0] running_i;
  reg [(DATA_W)-1:0] in0_i;
  // Outputs
  reg [(DATA_W)-1:0] out0_o;

  integer i;

  localparam CLOCK_PERIOD = 10;

  initial clk_i = 0;
  always #(CLOCK_PERIOD/2) clk_i = ~clk_i;
  `define ADVANCE @(posedge clk_i) #(CLOCK_PERIOD/2);

  Relu uut (
    .clk(clk_i),
    .rst(rst_i),
    .running(running_i),
    .in0(in0_i),
    .out0(out0_o)
  );


  initial begin
    `ifdef VCD;
    $dumpfile("uut.vcd");
    $dumpvars();
    `endif // VCD;
    rst_i = 0;
    running_i = 0;
    in0_i = 0;

    `ADVANCE;
    rst_i = 1;
    `ADVANCE;
    rst_i = 0;

    `ADVANCE;
    running_i = 1;

    for(i=0;i<8;i=i+1) begin
      running_i = i[0];
      in0_i = { i[2], {(DATA_W-1){i[1]}} };
      `ADVANCE;
    end

    `ADVANCE;

    in0_i = 0;
    running_i = 0;

    `ADVANCE;

    $finish();
  end

endmodule
// verilator coverage_on
