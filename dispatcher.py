#!/usr/bin/env python2.6
# encoding: utf-8
"""
dispatcher.py

Created by Brian Lalor on 2009-06-15.
Copyright (c) 2009 __MyCompanyName__. All rights reserved.
"""

## http://effbot.org/zone/thread-synchronization.htm
from __future__ import with_statement

import sys, os
import signal
import time
import daemonizer

import SocketServer, socket
import logging, logging.handlers

import threading
import Queue

import xbee, serial
import struct
import cPickle as pickle

# class XBeeDispatcher(SocketServer.ThreadingUnixStreamServer):
class XBeeDispatcher(SocketServer.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    
    def __init__(self, address, ser):
        self.serial = ser
        
        self._logger = logging.getLogger(self.__class__.__name__)
        
        # SocketServer.ThreadingUnixStreamServer.__init__(self, address, XBeeRequestHandler)
        SocketServer.TCPServer.__init__(self, address, XBeeRequestHandler)
    
    def server_activate(self):
        self.__shutdown = False
        
        self.__active_clients = []
        self.__active_clients_lock = threading.RLock()
        
        self.__serial_write_lock = threading.RLock()
        
        # SocketServer.ThreadingUnixStreamServer.server_activate(self)
        SocketServer.TCPServer.server_activate(self)
        
        self._logger.info('request queue size: %d', self.request_queue_size)
        
        ## start XBee communication thread here
        self.xbee_thread = xbee.XBee(self.serial, callback = self.dispatch_packet)
        
    
    
    def serve_forever(self):
        while not self.__shutdown:
            self.handle_request()
    
    
    def server_close(self):
        self.__shutdown = True
        
        # SocketServer.ThreadingUnixStreamServer.server_close(self)
        SocketServer.TCPServer.server_close(self)
        
        ## close down XBee comm thread
        self.xbee_thread.halt()
        self.serial.close()
        del self.xbee_thread
        
    
    
    def add_active_client(self, client):
        with self.__active_clients_lock:
            if client not in self.__active_clients:
                self.__active_clients.append(client)
    
    
    def remove_active_client(self, client):
        with self.__active_clients_lock:
            if client in self.__active_clients:
                self.__active_clients.remove(client)
    
    
    def dispatch_packet(self, packet):
        found_clients = False
        
        with self.__active_clients_lock:
            for client in self.__active_clients:
                found_clients = True
                client.enqueue_packet(packet)
        
        
        if not found_clients:
            self._logger.error("no active clients")
    
    
    def send_packet(self, name, **kwargs):
        with self.__serial_write_lock:
            self.xbee_thread.send(name, **kwargs)
        
    


class XBeeRequestHandler(SocketServer.BaseRequestHandler):
    def __init__(self, request, client_address, server):
        self._logger = logging.getLogger(self.__class__.__name__)
        
        SocketServer.BaseRequestHandler.__init__(self, request, client_address, server)
    
    
    def enqueue_packet(self, packet):
        try:
            self.packet_queue.put(packet)
        except Queue.Full:
            self._logger.error("queue is full!")
    
    
    def setup(self):
        self.packet_queue = Queue.Queue()
        
        ## add ourselves to the server's list of active clients
        self.server.add_active_client(self)
        
        ## think this might only work with TCP sockets
        self.request.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self._logger.debug("new connection")
    
    
    def handle(self):
        ## we *must* ensure that finish() gets called, which only happens when
        ## handle() returns successfully.
        
        header_len = struct.calcsize('!I')
        
        try:
            connection_alive = True
            
            while connection_alive:
                # enable short timeout for receiving data
                self.request.settimeout(0.25)
                
                try:
                    header_dat = self.request.recv(header_len, socket.MSG_WAITALL)
                    if len(header_dat) == 0:
                        self._logger.info('peer closed the connection')
                        connection_alive = False
                        continue
                    elif len(header_dat) != header_len:
                        self._logger.error('%d bytes for header, need %d: %s', len(header_dat), header_len, " ".join(['%.2x' % (ord(c),) for c in header_dat]))
                    else:
                        data_len = struct.unpack('!I', header_dat)[0]
                        packet = pickle.loads(self.request.recv(data_len, socket.MSG_WAITALL))
                        self.server.send_packet(packet[0], **packet[1])
                except socket.timeout:
                    # timeout reading data
                    pass
                
                # disable the timeout for sending data
                self.request.settimeout(None)
                
                try:
                    # pull a packet from the queue, with a blocking timeout
                    packet = self.packet_queue.get(True, 1)
                    data = pickle.dumps(packet, pickle.HIGHEST_PROTOCOL)
                    
                    self.request.sendall(struct.pack('!I', len(data)))
                    self.request.sendall(data)
                except Queue.Empty:
                    pass
                except socket.error:
                    self._logger.error("socket error sending packet to client", exc_info = True)
                    
                    connection_alive = False
                    
                    
        except:
            self._logger.error("exception handling request", exc_info = True)
        
    
    def finish(self):
        ## don't do anything too fancy in here; since we're using daemon
        ## threads, this isn't called when the server's shutting down.
        
        ## remove ourselves from the server's list of active clients
        self.server.remove_active_client(self)
        
        ## close the socket
        self.request.shutdown(socket.SHUT_RDWR)
        self.request.close()
    


def main():
    basedir = os.path.abspath(os.path.dirname(__file__))
    
    daemonizer.createDaemon()
    
    handler = logging.handlers.RotatingFileHandler(basedir + "/logs/dispatcher.log",
                                                   maxBytes=(5 * 1024 * 1024),
                                                   backupCount=5)
    
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s -- %(message)s"))
    
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    
    server = XBeeDispatcher(
        # "socket",
        ('', 9999),
        serial.Serial(port=sys.argv[1], baudrate=int(sys.argv[2]),rtscts=True)
    )
    
    # The signals SIGKILL and SIGSTOP cannot be caught, blocked, or ignored.
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    signal.signal(signal.SIGQUIT, lambda signum, frame: server.server_close())
    signal.signal(signal.SIGTERM, lambda signum, frame: server.server_close())
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Interrupt caught, shutting down")
    finally:
        logging.debug("cleaning up")
        server.server_close()
        # os.unlink("socket")
        logging.shutdown()
    


if __name__ == '__main__':
    main()

