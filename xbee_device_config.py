#!/usr/bin/env python
# encoding: utf-8
"""
xbee_device_config.py

Created by Brian Lalor on 2010-10-30.
Copyright (c) 2010 __MyCompanyName__. All rights reserved.
"""

import sys
import getopt

import socket, XBeeProxy

from pprint import pprint

help_message = '''
The help message goes here.
'''

ALL_PARAMETERS = (
    # addressing:
    'DH',
    'DL',
    'MY',
    'MP',
    'NC',
    'SH',
    'SL',
    'NI',
    'SE',
    'DE',
    'CI',
    'NP',
    'DD',
    
    # networking:
    'CH',
    'ID',
    'OP',
    'NH',
    'BH',
    'OI',
    'NT',
    'NO',
    'SC',
    'SD',
    'ZS',
    'NJ',
    'JV',
    'NW',
    'JN',
    'AR',
    
    # security:
    'EE',
    'EO',
    'NK',
    # 'KY', write only
    
    # rf interfacing:
    'PL',
    'PM',
    'DB',
    'PP',
    
    # serial interfacing (i/o):
    'AP',
    'AO',
    'BD',
    'NB',
    'SB',
    'RO',
    'D7',
    'D6',
    
    # i/o commands:
    'IR',
    'IC',
    'P0',
    'P1',
    'P2',
    'P3',
    'D0',
    'D1',
    'D2',
    'D3',
    'D4',
    'D5',
    'D8',
    'LT',
    'PR',
    'RP',
    '%V',
    'V+',
    'TP',
    
    # diagnostics:
    'VR',
    'HV',
    'AI',
    
    # at commands:
    'CT',
    'GT',
    'CC',
    
    # sleep commands:
    'SM',
    'SN',
    'SP',
    'ST',
    'SO',
    'WH',
    'PO',
)

def addr_to_bin(addr):
    return "".join(chr(int(x, 16)) for x in addr.split(":"))


def send_and_wait():
    pass


class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg


def main(argv=None):
    if argv is None:
        argv = sys.argv
    
    
    set_addr = None
    set_all = False
    config_file = None
    point_to_me = False
    
    query_addr = None
    
    host = None
    port = None
    
    try:
        try:
            opts, args = getopt.getopt(
                argv[1:],
                "hS:sQ:f:H:P:",
                ["help",
                 "set=",
                 "set-all",
                 "query-all=",
                 "config-file=",
                 "point-to-me",
                 "host=", "port="]
            )
        except getopt.error, msg:
            raise Usage(msg)
    
        # option processing
        for option, value in opts:
            if option in ("-h", "--help"):
                raise Usage(help_message)
            
            if option in ("--set", "-S"):
                set_addr = value
            
            if option in ("--set-all", "-s"):
                set_all = True
            
            if option in ("--query-all", "-Q"):
                query_addr = value
            
            if option in ("--config-file", "-f"):
                config_file = value
            
            if option in ("--host", "-H"):
                host = value
            
            if option in ("--port", "-P"):
                port = int(value)
            
            if option in ("--point-to-me",):
                point_to_me = True
            
        
        if (host == None) or (port == None):
            raise Usage("must specify port and host")
        
        if (set_addr != None) and set_all:
            raise Usage("set and set-all are mutually exclusive")
        
        if (set_addr != None) or set_all:
            if query_addr != None:
                raise Usage("query and set operations are mutually exclusive")
            
            if config_file == None:
                raise Usage("must have a config file to set parameters")
        elif query_addr == None:
            raise Usage("must select a set or query command")
        
        
    except Usage, err:
        print >> sys.stderr, sys.argv[0].split("/")[-1] + ": " + str(err.msg)
        print >> sys.stderr, "\t for help use --help"
        return 2
    
    
    _socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    _socket.connect((host, port))
    
    xbee = XBeeProxy.XBeeProxy(_socket)
    
    frame_id = chr(1)
    
    if (set_addr != None) or set_all:
        CONFIG_DATA = __import__(config_file).CONFIG_DATA
        
        if set_all:
            sections = CONFIG_DATA.keys()
        else:
            sections = [set_addr]
        
        SH, SL = None, None
        
        if point_to_me:
            # retrieve our SH and SL
            xbee.at(command = 'SH', frame_id = '1')
            xbee.at(command = 'SL', frame_id = '2')
            
            while (SH == None) or (SL == None):
                frame = xbee.wait_read_frame()
                if (frame['id'] == 'at_response') and (frame['frame_id'] == '1') and (frame['command'] == 'SH'):
                    SH = frame['parameter']
                elif (frame['id'] == 'at_response') and (frame['frame_id'] == '2') and (frame['command'] == 'SL'):
                    SL = frame['parameter']
            
        for section in sections:
            addr = addr_to_bin(section)
            
            if point_to_me:
                CONFIG_DATA[section]['DH'] = SH
                CONFIG_DATA[section]['DL'] = SL
            
            # need AC as the last command, to make it take effect
            for opt in CONFIG_DATA[section].keys():
                val = CONFIG_DATA[section][opt]
                
                print section, opt, val
                
                resend = True
                while resend:
                    frame_id = chr(ord(frame_id) + 1)
                    xbee.remote_at(command = opt, frame_id = frame_id, dest_addr_long = addr, parameter = val)
                    
                    while True:
                        frame = xbee.wait_read_frame()
                        print frame
                        if (frame['id'] == 'remote_at_response') and \
                           (frame['frame_id'] == frame_id) and \
                           (frame['source_addr_long'] == addr):
                           
                            if frame['status'] == '\x00':
                                resend = False
                            elif frame['status'] == '\x04':
                                print >>sys.stderr, "timeout"
                            else:
                                resend = False
                                print >>sys.stderr, "error setting %s: %02X" % (opt, ord(frame['status']))
                            break
            
            print 'sending "AC"'
            resend = True
            while resend:
                frame_id = chr(ord(frame_id) + 1)
                xbee.remote_at(command = 'AC', frame_id = frame_id, dest_addr_long = addr)
                
                while True:
                    frame = xbee.wait_read_frame()
                    print frame
                    if (frame['id'] == 'remote_at_response') and (frame['frame_id'] == frame_id) and (frame['source_addr_long'] == addr):
                        if frame['status'] == '\x00':
                            resend = False
                        elif frame['status'] == '\x04':
                            print >>sys.stderr, "timeout"
                        else:
                            resend = False
                            print >>sys.stderr, "error querying %s: %02X" % (opt, ord(frame['status']))
                        break
            
            
        
    else:
        # query
        addr = addr_to_bin(query_addr)
        
        data = {}
        for opt in ALL_PARAMETERS:
            opt = opt.upper()
            # print section, opt
            
            resend = True
            while resend:
                frame_id = chr(ord(frame_id) + 1)
                xbee.remote_at(command = opt, frame_id = frame_id, dest_addr_long = addr)
                
                while True:
                    frame = xbee.wait_read_frame()
                    # print frame
                    if (frame['id'] == 'remote_at_response') and (frame['frame_id'] == frame_id) and (frame['source_addr_long'] == addr):
                        if frame['status'] == '\x00':
                            resend = False
                            if 'parameter' in frame:
                                val = frame['parameter']
                                # val = "0x" + "".join('%02X' % ord(x) for x in frame['parameter'])
                                # print query_addr, opt, " ".join('%02X' % ord(x) for x in frame['parameter'])
                                # print opt, val #, "(%d)" % int(val, 16)
                                data[opt] = val
                            else:
                                print >>sys.stderr, "no parameter in frame for command %s!" % opt
                                print >>sys.stderr, frame
                        elif frame['status'] == '\x04':
                            print "timeout"
                        else:
                            resend = False
                            print >>sys.stderr, "error querying %s: %02X" % (opt, ord(frame['status']))
                            
                        break
                    
        pprint(data)
    
    print "cleaning up"
    xbee.halt()
    _socket.shutdown(socket.SHUT_RDWR)
    _socket.close()


if __name__ == "__main__":
    sys.exit(main())