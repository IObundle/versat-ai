def setup(py_params_dict):
    attributes_dict = {
        "generate_hw": False,
        "confs": [
            {
                "name": "ADDR_WIDTH",
                "descr": "",
                "type": "P",
                "val": "32",
                "min": "1",
                "max": "32",
            },
            {
                "name": "DATA_WIDTH",
                "descr": "",
                "type": "P",
                "val": "32",
                "min": "1",
                "max": "1024",
            },
        ],
        "ports": [
            {
                "name": "clk_en_rst_s",
                "signals": {
                    "type": "iob_clk",
                },
                "descr": "Clock, clock enable and reset",
            },
            {
                "name": "axi_s0_s",
                "descr": "Manager AXI interface",
                "signals": {
                    "type": "axi",
                    "prefix": "s00_",
                    "ADDR_W": "AXI_ADDR_W",
                    "DATA_W": "AXI_DATA_W",
                    "LEN_W": "AXI_LEN_W",
                },
            },
            {
                "name": "axi_s1_s",
                "descr": "Subordinate AXI interface",
                "signals": {
                    "type": "axi",
                    "prefix": "s01_",
                    "ADDR_W": "AXI_ADDR_W",
                    "DATA_W": "AXI_DATA_W",
                    "LEN_W": "AXI_LEN_W",
                },
            },
            {
                "name": "axi_m",
                "descr": "Subordinate AXI interface",
                "signals": {
                    "type": "axi",
                    "prefix": "m00_",
                    "ADDR_W": "AXI_ADDR_W",
                    "DATA_W": "AXI_DATA_W",
                    "LEN_W": "AXI_LEN_W",
                },
            },
        ],
    }

    return attributes_dict
