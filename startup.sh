#!/bin/sh -ex

cd $(dirname $0)
./xbee_gateway.py /dev/ttyUSB0 115200
./xbee_network_monitor.py
./xmlrpc_server.py
./db_logging_receiver.py
./environmental_node_consumer.py
./furnace_consumer.py
./power_consumer.py
./xbee_lt_sensor.py
./fuel_oil_tank_consumer.py
./sprinkler_driver.py
./voltometer_driver.py
