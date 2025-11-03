`timescale 1ns / 1ps

// verilator coverage_off
module MyFloatAccum_tb (

);
  localparam DATA_W = 32;
  localparam DELAY_W = 32;
  localparam STRIDE_W = 32;
  localparam EXP_W = 8;

  // Inputs
  reg [(1)-1:0] clk_i;
  reg [(1)-1:0] rst_i;
  reg [(1)-1:0] run_i;
  reg [(1)-1:0] running_i;
  reg [(STRIDE_W)-1:0] strideMinusOne_i;
  reg [(DATA_W)-1:0] in0_i;
  reg [(DELAY_W)-1:0] delay0_i;
  // Outputs
  reg [(DATA_W)-1:0] out0_o;

  integer i;
  integer d;

  reg [3:0] flt_accum_counter;

  localparam CLOCK_PERIOD = 10;

  initial clk_i = 0;
  always #(CLOCK_PERIOD/2) clk_i = ~clk_i;
  `define ADVANCE @(posedge clk_i) #(CLOCK_PERIOD/2);

  MyFloatAccum #(
    .DATA_W(DATA_W),
    .STRIDE_W(STRIDE_W),
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

  task Float_Accum (input [DATA_W-1:0] m_a);
  begin

    `ADVANCE;

    run_i = 1;
    in0_i = m_a;

    `ADVANCE;

    run_i = 0;
    running_i = 1;

    flt_accum_counter = 4'd6;
    while(flt_accum_counter > 0) begin
        `ADVANCE;
        flt_accum_counter = flt_accum_counter - 1;
    end

    running_i = 0;

  end
  endtask


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
    `ADVANCE;
    rst_i = 0;

    // input stimuli
    `ADVANCE;
    delay0_i = {DELAY_W{1'b1}};


    `ADVANCE;
    delay0_i = 0;
    strideMinusOne_i = {STRIDE_W{1'b1}};
    `ADVANCE;
    rst_i = 0;

    delay0_i = 0;
    strideMinusOne_i = 0;

    for(d=0;d<4;d=d+1) begin
      delay0_i = {DELAY_W{d[0]}};

      for(i=0;i<4;i=i+1) begin
        Float_Accum({DATA_W{i[0]}});
      end
    end

    `ADVANCE;
    rst_i = 1;
    `ADVANCE;
    rst_i = 0;
    `ADVANCE;

    // accum stimuli
    delay0_i = 0;
    strideMinusOne_i = 0;
    Float_Accum(32'hFF800000);

    for(d=0;d<(2**EXP_W);d=d+1) begin
      Float_Accum({1'b0, d[EXP_W-1:0], {(32-1-EXP_W-1){1'b0}}, 1'b1 });
    end

    for(d=0;d<(2**EXP_W);d=d+1) begin
      Float_Accum({1'b1, d[EXP_W-1:0], {(32-1-EXP_W-1){1'b0}}, 1'b1 });
    end

    Float_Accum(32'hFF800000);

    `ADVANCE;
    rst_i = 1;
    `ADVANCE;
    rst_i = 0;
    `ADVANCE;

    $finish();
  end

endmodule
// verilator coverage_on
