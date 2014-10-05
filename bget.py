import sys
import hashlib
import math
import socket
import array
import pprint
import struct
import time
import urllib
import os
import random
import threading
import pickle

import bencode
import bittorrent

MSG_CHOKE = '\x00'
MSG_UNCHOKE = '\x01'
MSG_INTERESTED = '\x02'
MSG_UNINTERESTED = '\x03'
MSG_HAVE = '\x04'
MSG_BITFIELD = '\x05'
MSG_REQUEST = '\x06'
MSG_PIECE = '\x07'
MSG_CANCEL = '\x08'
BLOCKSIZE = 16384

verbose = True

available_peers = set()
invalid_peers = set()
using_peers = set()
total_bytes = 0
downloaded_bytes = {}
download_rate = 0
total_pieces = 0
peers = []
excluded_peers = []
peer_connections = {}
peer_states = {}
peer_pieces = {}
clientid = os.urandom(20)
peer_lock = threading.Lock()

def get_freepeer(tid):
    if peers:
        peer = random.choice(peers)
        peers.remove(peer)
        excluded_peers.append(peer)
        peer_connections[tid] = peer['ip'] + ':' + str(peer['port'])
        return peer
    else:
        return None

def get_freepiece():
    with peer_lock:
        for i in range(len(pieces)):
            if pieces[i] == 0 :
                pieces[i] = 1
                return i
        else:
            return None

def update_peer_list(tracker):
    np = parse_peers(tracker['peers'])
    for peer in np:
        if peer not in excluded_peers:
            peers.append(peer)

def handshake(infohash, clientid):
    ret = ''
    ret += chr(19)
    ret += 'BitTorrent protocol'
    ret += '0' * 8
    ret += infohash
    ret += clientid
    return ret

def create_message(msgtype, **kwargs):
    msg = '' + msgtype
    if msgtype == MSG_REQUEST:
        msg += struct.pack('!III', kwargs['piece'], kwargs['begin'] * BLOCKSIZE, BLOCKSIZE)
    elif msgtype == MSG_HAVE:
        msg += struct.pack('!I', kwargs['piece'])
    length = len(msg)
    return struct.pack('!I', length) + msg

def peer_thread(torrent, clientid, tid):
    piece = ''
    blockid = 0
    blockammount = 16
    peer_choked = 1
    me_interested = 0
    downloaded = 1

    peer = get_freepeer(tid)
    if peer == None:
        peer_connections[tid] = 'No more peers left!'
        exit(1)

    while True:
        try:
            peer_states[tid] = 'Connecting...'
            if downloaded == 1:
                piecen = get_freepiece()
                if piecen != None:
                    peer_pieces[tid] = piecen
                else:
                    peer_states[tid] = 'Exited, no more pieces left'
                    exit(1)
            downloaded = 0

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            try:
                s.connect((peer['ip'], peer['port']))
            except:
                peer_states[tid] = 'Connection failed'
                peer = get_freepeer(tid)
                if peer == None:
                    peer_connections[tid] = 'No more peers left!'
                continue
            s.settimeout(None)
            peer_states[tid] = 'Connected'
            s.send(handshake(torrent.hash, clientid))
            hand = s.recv(68)
            if hand == '':
                peer_states[tid] = 'Handshake not returned!'
                peer = get_freepeer(tid)
                if peer == None:
                    peer_connections[tid] = 'No more peers left!'
                continue
            peer_states[tid] = 'Handshaked'
            s.send(create_message(MSG_INTERESTED))
            while downloaded == 0:
                data = s.recv(4)
                if data=='':
                    peer_states[tid] = 'Connection broken!'
                    exit(1)
                length = struct.unpack('!I', data)[0]
                if length == 0:
                    continue
                msgtype = s.recv(1)
                length -= 1
                if msgtype == MSG_UNCHOKE:
                    peer_states[tid] = 'Unchoked peer'
                    s.send(create_message(MSG_UNCHOKE))
                    s.send(create_message(MSG_INTERESTED))
                    s.send(create_message(MSG_REQUEST, piece=piecen, begin=blockid))
                elif msgtype == MSG_PIECE:
                    peer_states[tid] = 'Receiving data'
                    data = s.recv(8)
                    index, begin = struct.unpack('!II', data)
                    length -= 8
                    data = ''
                    while length:
                        input = s.recv(2048)
                        length -= len(input)
                        register_download(tid, len(input))
                        data += input
                    piece += data
                    blockid += 1
                    if blockid == 16:
                        peer_states[tid] = 'Piece finished'
                        sha1 = hashlib.sha1(piece).digest()
                        peer_states[tid] = 'Sha success'
                        write_piece(torrent, piecen, piece)
                        pieces[piecen] = 2
                        downloaded = 1
                        s.send(create_message(MSG_HAVE, piece=piecen))
                    else:
                        s.send(create_message(MSG_REQUEST, piece=piecen, begin=blockid))
                else:
                    more = s.recv(length)
        except:
            raise
            peer_states[tid] = 'Exception!'
            peer = get_freepeer(tid)
            if peer == None:
                peer_connections[tid] = 'No more peers left!'
                exit(1)
            downloaded = 0
            continue

    return 0

def register_download(thread, bytes):
    if bytes > 0:
        t = time.time()
        downloaded_bytes[thread] += bytes

def main():
    if len(sys.argv) <= 1:
        print 'Usage: bget <torrentpath>'
        exit(1)

    total_length = 0

    try:
        torrent = bittorrent.Torrent(sys.argv[1])
    except Exception as e:
        print 'Torrent imposible to read:', str(e)
        exit(1)

    torrent.show()

    pammount = len(torrent.data['info']['pieces']) / 20
    pieces = [0] * pammount
    total_bytes = total_length
    total_pieces = pammount

    torrent.start()

    tracker = bittorrent.Tracker(torrent.data['announce'])
    tracker_data = tracker.get(torrent, clientid)

    if False:
        tracker = read_tracker(torrent['announce'], torrent.hash, clientid, total_length)
        if not tracker:
            exit(1)
        print '  Updating peer list'
        update_peer_list(tracker)
        print '  %d peers found'%(len(peers),)
        print
        f = open('/tmp/peers.pkl', 'w')
        pickle.dump(peers, f)
        f.close()
    else:
        print '  Loading peers from pickle file'
        f = open('/tmp/peers.pkl', 'r')
        peers = pickle.load(f)
        f.close()

    threads = 10
    thread_list = []

    for i in range(threads):
        peer_connections[i] = 'None'
        peer_states[i] = 'Not connected'
        peer_pieces[i] = -1
        downloaded_bytes[i] = 0
        th = threading.Thread(target=peer_thread, args=(torrent, clientid, i))
        thread_list.append(th)
        th.start()

    fmt = '{0:4} {1:5} {2:24} {3}'

    def update_status():
        downloaded = sum(downloaded_bytes.values())
        downloaded_pieces = len(filter(lambda x:x==2, pieces))
        percent = downloaded * 100.0 / total_bytes
        downloaded_chars = int(math.floor(percent * 80 / 100))
        left_chars = 80 - downloaded_chars
        if verbose:
            print '%9d/%09d bytes downloaded (%3.2f %%), %4d/%4d pieces, %d peers left'%(downloaded, total_bytes, percent, downloaded_pieces, total_pieces, len(peers))
        else:
            for i in range(threads):
                print '\033[K' + fmt.format(i, peer_pieces[i], peer_connections[i], peer_states[i])
            print '\033[K  %9d/%09d bytes downloaded (%3.2f %%), %4d/%4d pieces, %d peers left'%(downloaded, total_bytes, percent, downloaded_pieces, total_pieces, len(peers))
            print '\033[K [' + '#' * downloaded_chars + ' ' * left_chars + ']'
            sys.stdout.write('\033[' + str(threads + 2) + 'A')

    if verbose==False:
        print '\033[1;1m' + fmt.format('', 'Index', 'Connection', 'State') + '\033[0m'

    sys.stdout.flush()

    while True:
        update_status()
        time.sleep(1)
        if len(peers) < 10:
            tracker = read_tracker(torrent['announce'], torrent.hash, clientid, total_length)
            if not tracker:
                exit(1)
            update_peer_list(tracker)

if __name__=='__main__':
    main()
