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
                "name": "S_DATA_WIDTH",
                "descr": "",
                "type": "P",
                "val": "32",
                "min": "1",
                "max": "512",
            },
            {
                "name": "M_DATA_WIDTH",
                "descr": "",
                "type": "P",
                "val": "32",
                "min": "1",
                "max": "512",
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
                    "ADDR_W": "ADDR_WIDTH",
                    "DATA_W": "M_DATA_WIDTH",
                },
            },
            {
                "name": "axi_s",
                "descr": "Subordinate AXI interface",
                "signals": {
                    "type": "axi",
                    "prefix": "s_",
                    "ADDR_W": "ADDR_WIDTH",
                    "DATA_W": "S_DATA_WIDTH",
                },
            },
        ],
    }

    return attributes_dict
