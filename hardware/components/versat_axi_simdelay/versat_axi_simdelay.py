def setup(py_params_dict):
    attributes_dict = {
        "generate_hw": False,
        "confs": [
            {
                "name": "AXI_ADDR_W",
                "descr": "",
                "type": "P",
                "val": "32",
                "min": "1",
                "max": "32",
            },
            {
                "name": "AXI_DATA_W",
                "descr": "",
                "type": "P",
                "val": "32",
                "min": "1",
                "max": "32",
            },
            {
                "name": "AXI_LEN_W",
                "descr": "",
                "type": "P",
                "val": "8",
                "min": "1",
                "max": "32",
            },
            {
                "name": "AXI_ID_WIDTH",
                "descr": "",
                "type": "P",
                "val": "4",
                "min": "1",
                "max": "32",
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
                "name": "axi_m",
                "descr": "Manager AXI interface",
                "signals": {
                    "type": "axi",
                    "prefix": "m_",
                    "ADDR_W": "AXI_ADDR_W",
                    "DATA_W": "AXI_DATA_W",
                    "LEN_W": "AXI_LEN_W",
                },
            },
            {
                "name": "axi_s",
                "descr": "Subordinate AXI interface",
                "signals": {
                    "type": "axi",
                    "prefix": "s_",
                    "ADDR_W": "AXI_ADDR_W",
                    "DATA_W": "AXI_DATA_W",
                    "LEN_W": "AXI_LEN_W",
                },
            },
        ],
    }

    return attributes_dict
