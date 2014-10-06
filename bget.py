import math
import os
import random
import struct
import sys
import time
import threading

import bencode
import bittorrent

verbose = True

pieces = []
peer_whitelist = set()
peer_blacklist = set()
peer_connections = {}

peer_lock = threading.Lock()

def get_freepeer():
    with peer_lock:
        if peer_whitelist:
            peer = random.choice(tuple(peer_whitelist))
            peer_whitelist.remove(peer)
            peer_blacklist.add(peer)
            return peer
        else:
            return None

def get_freepiece(torrent):
    with peer_lock:
        for i in range(len(torrent.pieces)):
            if torrent.pieces[i] == 0 :
                torrent.pieces[i] = 1
                return i
        return None

def update_peers(tracker):
    peers = tracker.peers()
    peer_whitelist.update(peers - peer_blacklist)

def peer_thread(torrent, clientid, tid):
    BLOCKSIZE = 16384

    def newpeer():
        while True:
            try:
                peer = get_freepeer()
                pc = bittorrent.PeerConnection(peer)
                peer_connections[tid] = pc
                pc.connect()
                if pc.handshake(torrent, clientid) == False:
                    continue
                pc.send(bittorrent.MSG_INTERESTED)
                break
            except:
                continue
        return pc

    pc = newpeer()
    piece_data = bytearray(int(torrent.data['info']['piece length']))
    pc.piece = get_freepiece(torrent)
    blocks = int(torrent.data['info']['piece length']) / BLOCKSIZE
    blockid = 0

    while True:
        try:
            mtype, mdata = pc.receive()
        except:
            pc = newpeer()
            continue

        if mtype == bittorrent.MSG_UNCHOKE:
            pc.state = 'Ready to receive'
            pc.send(bittorrent.MSG_REQUEST, piece=pc.piece, begin=blockid * BLOCKSIZE, length=BLOCKSIZE)
        elif mtype == bittorrent.MSG_CHOKE:
            pc.state = 'Chocked!'
        elif mtype == bittorrent.MSG_PIECE:
            pc.state = 'Receiving data'
            index, begin = struct.unpack('!II', mdata[0:8])
            data = mdata[8:]
            piece_data[begin:begin+len(data)] = data
            torrent.register(len(data))
            blockid += 1
            if blockid == blocks:
                blockid = 0
                if torrent.checkpiece(index, piece_data):
                    torrent.writepiece(index, piece_data)
                    pc.piece = get_freepiece(torrent)
                    if pc.piece == None:
                        pc.state = 'Idle, no pieces left'
                        return
            pc.send(bittorrent.MSG_REQUEST, piece=pc.piece, begin=blockid * BLOCKSIZE, length=BLOCKSIZE)

def main():
    if len(sys.argv) <= 1:
        print 'Usage: bget <torrentpath>'
        exit(1)

    clientid = os.urandom(20)

    torrent = bittorrent.Torrent(sys.argv[1])
    torrent.show()
    torrent.start()

    tracker = bittorrent.Tracker(torrent.data['announce'])
    tracker.get(torrent, clientid)
    update_peers(tracker)

    threads = 10
    thread_list = []

    for i in range(threads):
        th = threading.Thread(target=peer_thread, args=(torrent, clientid, i))
        thread_list.append(th)
        th.start()

    fmt = '{0:<5} {1:24} {2:4} {3}'

    def update_status():
        downloaded = torrent.downloaded_bytes
        total_bytes = torrent.size
        percent = downloaded * 100.0 / total_bytes
        downloaded_chars = int(math.floor(percent * 80 / 100))
        left_chars = 80 - downloaded_chars
        for i in range(threads):
            if i in peer_connections.keys():
                if peer_connections[i].is_stalled():
                    peer_connections[i].drop()
                piece = peer_connections[i].piece
                peer = '{0[0]}:{0[1]}'.format(peer_connections[i].peer)
                dietime = int(peer_connections[i].timetodie)
                state = peer_connections[i].state
                print '\033[K' + fmt.format(piece, peer, dietime, state)
            else:
                print '\033[K' + '-'*40

        print '\033[K  %6d/%06d KiB (%3.2f %%) @ %8.2f KiB/s, %4d/%4d pieces, %d peers'% (torrent.downloaded_bytes/1024, torrent.size/1024, percent, torrent.rate, torrent.downloaded_pieces, 888, len(peer_whitelist))
        print '\033[K [' + '#' * downloaded_chars + '.' * left_chars + ']'
        sys.stdout.write('\033[' + str(threads + 2) + 'A')

    print '\033[1;1m' + fmt.format('Index', 'Connection', 'Die', 'State') + '\033[0m'

    sys.stdout.flush()

    while True:
        update_status()
        time.sleep(1)
        if tracker.get(torrent, clientid):
            update_peers(tracker)

if __name__=='__main__':
    main()
