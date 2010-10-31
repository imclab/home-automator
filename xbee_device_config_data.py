## config file for all XBee devices we know about

CONFIG_DATA = {
    '00:11:22:33:44:55:66:4d' : {
        ## furnace timer/monitor
        'NI' : 'Furnace',
        'BD' : '\x04',
    },
    '00:11:22:33:44:55:66:0a' : {
        ## power monitor
        'NI' : 'Power',
        'BD' : '\x04',
    },
    '00:11:22:33:44:55:66:22' : {
        ## temp/humidity 1

        'NI' : 'T/H Test 1',
        'BD' : '\x04',
    },
    '00:11:22:33:44:55:66:dc' : {
        ## temp/humidity 2
        'NI' : 'T/H Test 2',
        'BD' : '\x04',
    },
    '00:11:22:33:44:55:66:cf' : {
        ## fuel oil tank level monitor
        'NI' : 'Fuel Oil Tank',
        'BD' : '\x04',
    },
    '00:11:22:33:44:55:66:a5' : {
        ## XBee Light/Temperature 
        'NI' : 'L/T Sensor 1',

        ## DD[1] should be 0x03000E
        ## DH, DL need to be our SH, SL

        # Configure pins DI1, DI2 for analog input; DI3 if this has humidity capability (it doesn't)
        'D1' : '\x02',
        'D2' : '\x02',
        'D3' : '\x00',

        # Configure battery-monitor pin DIO11/P1 for digital input:
        'P1' : '\x03',

        ## following stolen from dia
        # Enable change detection on DIO11:
        #
        # 0x   8    0    0
        #   1000 0000 0000 (b)
        #   DDDD DDDD DDDD
        #   IIII IIII IIII
        #   OOOO OOOO OOOO
        #   1198 7654 3210
        #   10
        'IC' : '\x08\x00',

        ## IO sample rate: 60000ms; < 0xFFFF
        # 60000
        'IR' : '\xEA\x60',

        ## Wake Host; post-sleep delay before sending samples; 125ms
        'WH' : '\x7D',

        ## sleep setup
        # time before sleep; 1125ms
        'ST' : '\x04\x65',
        # number of sleep periods; 125
        'SN' : '\x7D',
        # sleep period (x10 ms; 48 = 480ms)
        'SP' : '\x30',
        # sleep options; always wake for ST time and sleep for entire SN*SP time
        'SO' : '\x06',
    },
    '00:11:22:33:44:55:66:7d' : {
        ## XBee wall router
        'NI' : 'Office Router',

        ## DD[1] should be ???
        ## DH, DL need to be our SH, SL

        # Configure pins DI1, DI2 for analog input
        'D1' : '\x02',
        'D2' : '\x02',

        # IO sample rate: 60000ms; < 0xFFFF
        'IR' : '\xEA\x60',
    },
}
