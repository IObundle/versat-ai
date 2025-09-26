# VersatAI sim_build.mk
# Imported by iob_system's sim_build.mk
CUSTOM_COVERAGE_FLAGS=cov_annotated
CUSTOM_COVERAGE_FLAGS+=-E iob_uut.v
CUSTOM_COVERAGE_FLAGS+=-E versat_ai_mwrap.v
CUSTOM_COVERAGE_FLAGS+=-E iob_rom_sp.v
CUSTOM_COVERAGE_FLAGS+=-E iob_uart.v
CUSTOM_COVERAGE_FLAGS+=-E iob_uart_core.v
CUSTOM_COVERAGE_FLAGS+=-E iob_uart_csrs.v
CUSTOM_COVERAGE_FLAGS+=-E iob_axi_ram.v
CUSTOM_COVERAGE_FLAGS+=-E iob_ram_t2p_be.v
CUSTOM_COVERAGE_FLAGS+=-E iob_ram_t2p.v
CUSTOM_COVERAGE_FLAGS+=-o versat_ai_coverage.rpt
