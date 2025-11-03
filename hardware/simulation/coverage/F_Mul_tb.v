`timescale 1ns / 1ps

// verilator coverage_off
module F_Mul_tb (

);
  localparam DATA_W = 32;
  localparam EXP_W = 8;
  // Inputs
  reg [(1)-1:0] clk_i;
  reg [(1)-1:0] rst_i;
  reg [(1)-1:0] running_i;
  reg [(DATA_W)-1:0] in0_i;
  reg [(DATA_W)-1:0] in1_i;
  // Outputs
  reg [(DATA_W)-1:0] out0_o;

  localparam BOT_MANTISSA_W = 4;
  localparam TOP_MANTISSA_W = (DATA_W+3-BOT_MANTISSA_W);
  reg [(DATA_W)-1:0] op_a_int;
  reg [(DATA_W)-1:0] op_b_int;

  reg [3:0] mul_counter;

  integer op_a;
  integer op_b;

  integer m_b;
  integer exp;

  localparam CLOCK_PERIOD = 10;

  initial clk_i = 0;
  always #(CLOCK_PERIOD/2) clk_i = ~clk_i;
  `define ADVANCE @(posedge clk_i) #(CLOCK_PERIOD/2);

  F_Mul #(
      .DATA_W(DATA_W)
  ) uut (
    .clk(clk_i),
    .rst(rst_i),
    .running(running_i),
    .in0(in0_i),
    .in1(in1_i),
    .out0(out0_o)
  );

  task Mul (input [DATA_W-1:0] m_a, input [DATA_W-1:0] m_b);
  begin

    `ADVANCE;

    running_i = 1;
    in0_i = m_a;
    in1_i = m_b;

    `ADVANCE;

    mul_counter = 4'd6;
    while(mul_counter > 0) begin
        `ADVANCE;
        mul_counter = mul_counter - 1;
    end

    running_i = 0;

  end
  endtask

  initial begin
    `ifdef VCD;
    $dumpfile("uut.vcd");
    $dumpvars();
    `endif // VCD;
    clk_i = 0;
    rst_i = 0;
    running_i = 0;
    in0_i = 0;
    in1_i = 0;

    `ADVANCE;

    rst_i = 1;

    `ADVANCE;

    rst_i = 0;

    `ADVANCE;

    // special coverage
    for(op_a=0;op_a<4;op_a=op_a+1) begin
        op_a_int = { {(EXP_W+1){op_a[1]}}, {(DATA_W-EXP_W-1){op_a[0]}} };
        Mul(op_a_int, {DATA_W{1'b0}});
    end
    in0_i = 0;
    for(op_b=0;op_b<4;op_b=op_b+1) begin
        op_b_int = { {(EXP_W+1){op_b[1]}}, {(DATA_W-EXP_W-1){op_b[0]}} };
        Mul({DATA_W{1'b0}}, op_b_int);
    end
    in1_i = 0;

    // regular multiplications positive
    for(op_a=0;op_a<32;op_a=op_a+1) begin
        op_a_int = (1<<op_a);
        for(op_b=0;op_b<32;op_b=op_b+1) begin
            op_b_int = (1<<op_b);
            Mul(op_a_int, op_b_int);
        end
    end

    // regular multiplications negative result
    for(op_a=0;op_a<32;op_a=op_a+1) begin
        op_a_int = (32'hFFFF_FFFF<<op_a);
        for(op_b=0;op_b<32;op_b=op_b+1) begin
            op_b_int = (1<<op_b);
            Mul(op_a_int, op_b_int);
        end
    end

    // round coverage

    op_a_int = {1'b0, {EXP_W{1'b0}}, {(DATA_W-EXP_W-1){1'b1}}};
    for(exp=0;exp<(2**EXP_W);exp=exp+1) begin
        for(m_b=0;m_b<(2**BOT_MANTISSA_W);m_b=m_b+1) begin

            op_b_int = {1'b0, exp[EXP_W-1:0], { {TOP_MANTISSA_W{1'b1}}, {m_b[BOT_MANTISSA_W-1:0]} } };
            Mul(op_a_int, op_b_int);

            op_b_int = {1'b0, exp[EXP_W-1:0], { {TOP_MANTISSA_W{1'b0}}, {m_b[BOT_MANTISSA_W-1:0]} } };
            Mul(op_a_int, op_b_int);

        end
    end

    `ADVANCE;

    op_a_int = 0;
    op_b_int = 0;
    Mul(op_a_int, op_b_int);

    `ADVANCE;
    rst_i = 1;
    `ADVANCE;
    rst_i = 0;
    `ADVANCE;

    $finish();
  end

endmodule
// verilator coverage_on
