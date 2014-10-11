import getopt
import math
import os
import random
import struct
import sys
import time
import threading

import bencode
import bittorrent
import utils

# global client id used to communicate with the tracker
clientid = os.urandom(20)

def peer_thread(torrent, swarm, tid):
    # This thread should connect to a peer, or answer to a peer connection,
    # and provide with all the functionality needed to interact with it.
    # The PeerConnection object will help implementing the communication
    # protocol.
    BLOCKSIZE = 16384

    def newpeer():
        while True:
            peer = swarm.get_peer()
            pc = bittorrent.PeerConnection(torrent, peer)
            print '{0:4} Connecting with peer {1}:{2}'.format(tid, peer[0], peer[1])
            print '{0:4} {1}'.format(tid, 'Handshaking')
            pc.connect()
            if pc.handshake(clientid) == False:
                continue
            print '{0:4} {1}'.format(tid, 'Handshaked')
            #pc.send(bittorrent.MSG_INTERESTED)
            break
        return pc

    pc = newpeer()
    piece_data = bytearray(int(torrent.data['info']['piece length']))
    blocks = int(torrent.data['info']['piece length']) / BLOCKSIZE
    blockid = 0

    while True:
        mtype, mdata = pc.receive()
        print '{0:4} {1}'.format(tid, bittorrent.msgtostr(mtype, mdata))

#        if mtype == bittorrent.MSG_UNCHOKE:
#            pc.send(bittorrent.MSG_REQUEST, piece=pc.piece, begin=blockid * BLOCKSIZE, length=BLOCKSIZE)
#        elif mtype == bittorrent.MSG_PIECE:
#            index, begin = struct.unpack('!II', mdata[0:8])
#            data = mdata[8:]
#            piece_data[begin:begin+len(data)] = data
#            torrent.register(len(data))
#            blockid += 1
#            if blockid == blocks:
#                blockid = 0
#                if torrent.checkpiece(index, piece_data):
#                    torrent.writepiece(index, piece_data)
#                    if pc.piece == None:
#                        return
#            pc.send(bittorrent.MSG_REQUEST, piece=pc.piece, begin=blockid * BLOCKSIZE, length=BLOCKSIZE)

def update_status(torrent):
    print 'Downloaded: %d/%d KiB % %.2f KiB/s'%(torrent.downloaded_bytes/1024, torrent.size/1024, torrent.rate)

def main():

    options, files = getopt.getopt(sys.argv[1:], 'ivt:', ['info', 'verbose', 'threads:'])

    if len(files) < 1:
        print 'Usage: bget [-i|--info] [-v|--verbose] [-t|--threads <numthreads>] <torrentpath>'
        exit(1)

    for flag, value in options:
        if flag == '-v' or flag == '--verbose':
            utils.config['verbose'] = True
        elif flag == '-t' or flag == '--threads':
            utils.config['threads'] = int(value)
        elif flag == '-i' or flag == '--info':
            utils.config['info'] = True

    torrent = bittorrent.Torrent(files[0])
    torrent.show()

    if utils.config['info'] == True:
        exit(0)

    torrent.start()

    tracker = bittorrent.Tracker(torrent.data['announce'])
    tracker.update(torrent, clientid)

    swarm = bittorrent.Swarm()
    swarm.update_peers(tracker)

    threads = utils.config['threads']
    thread_list = []

    for i in range(threads):
        th = threading.Thread(target=peer_thread, args=(torrent, swarm, i))
        thread_list.append(th)
        th.start()

    while True:
        update_status(torrent)
        time.sleep(1)
        if tracker.update(torrent, clientid):
            update_peers(tracker)

if __name__=='__main__':
    main()
