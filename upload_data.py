#!/usr/bin/env python2.6
# -*- coding: utf-8 -*-

## This script should (probably?) be run via cron, every X minutes (probably
## 1-5 or so).  It moves all data from the source database, sensors.db, to
## the upload database, upload.db.  It then uploads the data to the remote
## server, where graphing, analysis, etc. is performed. This allows processes
## which are frequently inserting data into the database to do so unhindered.
## In the eventual case that the upload process either takes longer than a few
## seconds, or when the network connection is down, inserts into the primary
## database are unimpacted, and no data bound for the upstream server should
## be lost.

## upload.db has same schema for power and room_temp, but also has add'l
## upload_state table.
### create table upload_state (
###     table_name text not null,
###     prop_name text not null,
###     value text not null,
###     primary key (table_name, prop_name)
### );
### insert into upload_state values ('power', 'last_uploaded_timestamp', 0);
### insert into upload_state values ('room_temp', 'last_uploaded_timestamp', 0);
## use the "last_uploaded_timestamp" value to keep track of which records
## should get uploaded.  This'll make it possible to keep some data in the
## power table for real-time monitoring.

import os
import sqlite3
import logging, logging.handlers

# http://www.hackorama.com/python/upload.shtml
import urllib2
import MultipartPostHandler

import cPickle as pickle
import tempfile
from pprint import pprint

upload_url = "http://example.com/upload_data"

auth_handler = urllib2.HTTPDigestAuthHandler()
auth_handler.add_password("<basic http auth realm>", upload_url, "<userid>", "<password>")

urlopener = urllib2.build_opener(MultipartPostHandler.MultipartPostHandler,
                                 auth_handler)

TEMP_SENSOR_NODE_MAP = {
    '00:11:22:33:44:55:66:22' : 'office.temperature',
    '00:11:22:33:44:55:66:DC' : 'living_room.temperature',
    '00:11:22:33:44:55:66:A5' : 'garage.temperature',
    '00:11:22:33:44:55:66:7D' : 'basement.temperature',
}

HUMID_SENSOR_NODE_MAP = {
    '00:11:22:33:44:55:66:22': 'office.humidity',
    '00:11:22:33:44:55:66:DC': 'living_room.humidity',
}

def identity_map(row):
    return row


def temp_map(row):
    trow = list(row)
    trow[1] = TEMP_SENSOR_NODE_MAP[row[1].upper()]
    
    return trow


def humid_map(row):
    trow = list(row)
    trow[1] = HUMID_SENSOR_NODE_MAP[row[1].upper()]
    
    return trow


TABLE_TO_PICKLE_MAP = {
    'power' : ('power', ('ts_utc', 'clamp1', 'clamp2'), identity_map),
    'temperature' : ('temperature', ('ts_utc', 'node_id', 'temp_C'), temp_map),
    'humidity' : ('humidity', ('ts_utc', 'node_id', 'rel_humid'), humid_map),
    # 'light' : '',
    # 'furnace' : '',
    'oil_tank' : ('oil_tank', ('ts_utc', 'height'), identity_map),
}

def main():
    os.chdir(os.path.abspath(os.path.dirname(__file__)))
    log.info("starting up in %s" % (os.getcwd(),))
    
    conn = sqlite3.connect("upload.db", timeout = 30, isolation_level = "EXCLUSIVE")
    
    ## attach databases
    conn.execute("attach database 'sensors.db' as 'source'")
    log.debug("'source' attached")
    
    table_name = None
    proceed_with_upload = True
    
    try:
        with conn:
            ## walk through each table in the map
            for table_name in TABLE_TO_PICKLE_MAP:
                last_uploaded_rec = int(
                    conn.execute(
                        """
                        select value
                          from 'main'.upload_state
                         where table_name = ?
                           and prop_name = 'last_uploaded_timestamp'
                        """,
                        (table_name,)
                    ).fetchone()[0]
                )
                
                log.debug("last_uploaded_rec for %s is %d", table_name, last_uploaded_rec)
                
                ## insert rows into upload db
                query = """
                insert into 'main'.%(table_name)s
                    select * from 'source'.%(table_name)s
                     where 'source'.%(table_name)s.ts_utc > ?
                """ % {'table_name':table_name}
                log.debug("query: %s, args: %s", query, (last_uploaded_rec,))
                conn.execute(query, (last_uploaded_rec,))
                
                result = conn.execute(
                    "select max(ts_utc) from 'main'.%s" % (table_name,)
                ).fetchone()[0]
                
                if result != None:
                    last_uploaded_rec = int(result)
                else:
                    log.error("no last_uploaded_rec!")
                
                ## delete rows from source table
                conn.execute(
                    """delete from 'source'.%s where ts_utc < ?""" % (table_name,),
                    (last_uploaded_rec - (15 * 60),) # 15 minutes
                )
                
                ## update metadata table
                conn.execute(
                    """
                    update 'main'.upload_state
                       set value = ?
                     where table_name = ?
                       and prop_name = 'last_uploaded_timestamp'
                    """,
                    (last_uploaded_rec, table_name)
                )
                
                log.debug("done moving '%s'; last uploaded rec: %d", table_name, last_uploaded_rec)
            
    except:
        proceed_with_upload = False
        log.critical("unable to migrate data to upload.db for table %s", table_name, exc_info = True)
        
    conn.execute("detach 'source'")
    log.debug("'source' detached")
    
    if proceed_with_upload:
        # data to upload
        upload_pkg = {}
        
        with conn:
            ## start transaction, dump data to temp file
            for table_name in TABLE_TO_PICKLE_MAP:
                dict_key, columns, map_func = TABLE_TO_PICKLE_MAP[table_name]
                
                result = []
                select_query = "select %s from 'main'.%s" % (", ".join(columns), table_name)
                for row in conn.execute(select_query).fetchall():
                    result.append(map_func(row))
                
                if result:
                    upload_pkg[dict_key] = result
                    conn.execute("delete from 'main'.%s" % (table_name,))
            
            # pprint(upload_pkg)
            
            if upload_pkg:
                tmpf = tempfile.TemporaryFile()
                
                # pickle the dict
                log.debug("pickling")
                pickle.dump(upload_pkg, tmpf)
                
                # seek to the beginning of the temp file so that it can be read by the
                # uploader
                tmpf.seek(0)
                
                ## now, upload the data; 90 second timeout
                log.debug("uploading")
                resp = urlopener.open(upload_url, {'pickle_file': tmpf}, 90)
                
                if resp.code == 200:
                    # upload was successful
                    log.info("upload successful")
                else:
                    log.critical("FAILURE: %d -- %s" % (r.code, r.msg))
                
            else:
                log.warn("no data to upload")


if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))
    
    handler = logging.handlers.RotatingFileHandler('logs/uploader.log',
                                                   maxBytes=(5 * 1024 * 1024),
                                                   backupCount=5)
    
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(name)s -- %(message)s"))
    
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    
    log = logging.getLogger("uploader")
    
    try:
        main()
    except:
        log.critical("main() failed", exc_info = True)
    finally:
        logging.shutdown()
    

