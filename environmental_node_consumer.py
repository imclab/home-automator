#!/usr/bin/env python2.6
# -*- coding: utf-8 -*-

import sys, os
import consumer
import time

import threading
import struct

class Timeout(Exception):
    pass


class EnvironmentalNodeConsumer(consumer.BaseConsumer):
    # {{{ __init__
    def __init__(self, addrs):
        super(EnvironmentalNodeConsumer, self).__init__(addrs)
        
        self._register_rpc_function('environmental_node', self.read_calibration_data)
        # self._register_rpc_function('environmental_node', self.write_calibration_element)
        # self._register_rpc_function('environmental_node', self.perform_calibration)
        
        # short-term storage for retrieved calibration data
        self.__calibration_data = {}
        self.__calibration_data_lock = threading.RLock()
    
    
    # }}}
    
    # {{{ handle_packet
    def handle_packet(self, formatted_addr, frame):
        # {'id': 'zb_rx',
        #  'options': '\x01',
        #  'rf_data': 'T: 770.42 Cm: 375.14 RH:  42.88 Vcc: 3332 tempC:  19.04 tempF:  66.27\r\n',
        #  'source_addr': '\xda\xe0',
        #  'source_addr_long': '\x00\x13\xa2\x00@2\xdc\xdc'}
        
        # need to determine if this is regular sample data, or if it's a binary
        # response containing the current calibration data.  I wasn't very smart when
        # I wrote the code for the sensor, so there's binary data mixed in with sample
        # data. Try parsing the sample data first.
        handled_as_binary = False
        
        if len(frame['rf_data']) > 3:
            self._logger.debug("testing for binary")
            
            try:
                data_len = struct.unpack('<h', frame['rf_data'][:2])[0]
                data = struct.unpack('<7f', frame['rf_data'][2:])
                
                handled_as_binary = True
                
                with self.__calibration_data_lock:
                    self.__calibration_data[formatted_addr] = {
                        'capacitanceConvFactor': data[0],
                        'humiditySensitivity': data[1],
                        'temperatureCoefficient': data[2],
                        'calibratedHumidity': data[3],
                        'calibratedCapacitance': data[4],
                        'temperatureSensorCorrectionFactor': data[5],
                        'temperatureSensorCorrectionOffset': data[6],
                    }
                    
                    self._logger.debug("found calibration data: " + str(self.__calibration_data[formatted_addr]))
                
            except struct.error:
                pass
            
        
        if not handled_as_binary:
            # resume standard sample handling
            sdata = frame['rf_data'].strip().split()
            
            # Parse the sample
            # T: 778.21 Cm: 377.93 RH:  47.17 Vcc: 3342 tempC:  13.31 tempF:  55.96
            if sdata[0] == 'T:':
                rel_humid = float(sdata[5])
                temp_C = float(sdata[9])
                
                sensor_frame = {
                    'timestamp' : frame['_timestamp'],
                    'node_id'   : formatted_addr,
                    'rel_humid' : rel_humid,
                    'temp_C'    : temp_C,
                }
                
                self.publish_sensor_data('temperature.' + formatted_addr, sensor_frame)
                self.publish_sensor_data('humidity.' + formatted_addr, sensor_frame)
            else:
                self._logger.error("bad data: %s", unicode(frame['rf_data'], errors = 'replace'))
        
    
    # }}}
    
    # {{{ __build_message
    def __build_message(self, body):
        packet_spec = '<ch%dsB' % (len(body),)
        
        checksum = 0
        for d in body:
            checksum ^= ord(d)
        
        p = struct.pack(packet_spec, '*', len(body), body, checksum)
        
        return p
    
    # }}}
    
    # {{{ read_calibration_data
    # @param dest destination, formatted (xx:yy:zz:…)
    def read_calibration_data(self, dest):
        if not self._send_data(dest, self.__build_message('R')):
            raise Timeout("unable to send data")
        
        # 10s timeout to get response
        expiration = time.time() + 10
        while time.time() < expiration:
            with self.__calibration_data_lock:
                if dest in self.__calibration_data:
                    return self.__calibration_data.pop(dest)
        
        raise Timeout("timeout waiting for response")
    
    # }}}
    
    # {{{ write_calibration_element
    def write_calibration_element(self):
        pass
    
    # }}}
    
    # {{{ perform_calibration
    def perform_calibration(self):
        pass
    
    # }}}
    


def main():
    from support import daemonizer, log_config
    import signal
    import logging
    
    basedir = os.path.abspath(os.path.dirname(__file__))
    
    daemonizer.createDaemon()
    log_config.init_logging(basedir + "/logs/env_node.log")
    
    # log_config.init_logging_stdout()
    
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    
    c = EnvironmentalNodeConsumer((
        '00:11:22:33:44:55:66:dc',
        '00:11:22:33:44:55:66:22'
    ))
    
    try:
        c.process_forever()
    except:
        logging.error("unhandled exception", exc_info=True)
    finally:
        c.shutdown()
        log_config.shutdown()
    


if __name__ == '__main__':
    main()
