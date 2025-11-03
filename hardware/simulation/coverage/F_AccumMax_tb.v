`timescale 1ns / 1ps

// verilator coverage_off
module F_AccumMax_tb (

);
  localparam DATA_W = 8;
  localparam DELAY_W = 2;
  // Inputs
  reg [(1)-1:0] clk_i;
  reg [(1)-1:0] rst_i;
  reg [(1)-1:0] run_i;
  reg [(1)-1:0] running_i;
  reg [(DELAY_W)-1:0] strideMinusOne_i;
  reg [(DATA_W)-1:0] in0_i;
  reg [(DELAY_W)-1:0] delay0_i;
  // Outputs
  reg [(DATA_W)-1:0] out0_o;

  integer i;
  integer d;

  localparam CLOCK_PERIOD = 10;

  initial clk_i = 0;
  always #(CLOCK_PERIOD/2) clk_i = ~clk_i;
  `define ADVANCE @(posedge clk_i) #(CLOCK_PERIOD/2);

  F_AccumMax #(
    .DATA_W(DATA_W),
    .DELAY_W(DELAY_W)
  ) uut (
    .clk(clk_i),
    .rst(rst_i),
    .run(run_i),
    .running(running_i),
    .strideMinusOne(strideMinusOne_i),
    .in0(in0_i),
    .out0(out0_o),
    .delay0(delay0_i)
  );


  initial begin
    `ifdef VCD;
    $dumpfile("uut.vcd");
    $dumpvars();
    `endif // VCD;
    rst_i = 0;
    run_i = 0;
    running_i = 0;
    strideMinusOne_i = 0;
    in0_i = 0;
    delay0_i = 0;

    `ADVANCE;
    rst_i = 1;

    delay0_i = {DELAY_W{1'b1}};
    strideMinusOne_i = {DELAY_W{1'b1}};
    `ADVANCE;
    rst_i = 0;

    run_i = 1;
    delay0_i = 0;
    strideMinusOne_i = 0;

    for(d=0;d<(2**DELAY_W);d=d+1) begin
      delay0_i = d[DELAY_W-1:0];
      `ADVANCE;
      rst_i = 1;
      `ADVANCE;
      rst_i = 0;

      run_i = 1;

      for(i=0;i<(2**DATA_W);i=i+1) begin
        in0_i = i[DATA_W-1:0];
        `ADVANCE;
        run_i = 0;
        running_i = 1;
      end
      `ADVANCE;
      running_i = 0;
    end

    in0_i = 0;

    `ADVANCE;
    rst_i = 1;
    `ADVANCE;
    rst_i = 0;
    `ADVANCE;

    $finish();
  end

endmodule
// verilator coverage_on
