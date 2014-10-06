import os
import random
import struct
import sys
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
        else:
            return None

def update_peers(tracker):
    peers = tracker.peers()
    peer_whitelist.update(peers - peer_blacklist)

def peer_thread(torrent, clientid, tid):
    BLOCKSIZE = 16384
    peer = get_freepeer()
    pc = bittorrent.PeerConnection(peer)
    peer_connections[tid] = pc
    pc.connect()
    pc.handshake(torrent, clientid)

    pc.send(bittorrent.MSG_INTERESTED)
    piece_data = bytearray(int(torrent.data['info']['piece length']))
    piece = get_freepiece(torrent)
    blocks = int(torrent.data['info']['piece length']) / BLOCKSIZE
    blockid = 0

    while True:
        mtype, mdata = pc.receive()
        print tid, 'Message:', ord(mtype)
        if mtype == bittorrent.MSG_UNCHOKE:
            print tid, 'Unchoke!'
            pc.send(bittorrent.MSG_REQUEST, piece=piece, begin=blockid * BLOCKSIZE, length=BLOCKSIZE)
            print tid, 'Requested', piece, blockid
        elif mtype == bittorrent.MSG_PIECE:
            index, begin = struct.unpack('!II', mdata[0:8])
            data = mdata[8:]
            print tid, 'Received piece', index, begin
            piece_data[begin:begin+len(data)] = data
            blockid += 1
            if blockid == blocks:
                print tid, 'Finished with this piece!'
                check = torrent.checkpiece(index, piece_data)
                if check:
                    print 'ALL OK!'
                else:
                    print 'WOPS!'
                continue
            pc.send(bittorrent.MSG_REQUEST, piece=piece, begin=blockid * BLOCKSIZE, length=BLOCKSIZE)

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
        if tracker.get(torrent, clientid):
            update_peers(tracker)

if __name__=='__main__':
    main()
