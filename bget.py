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

def peer_thread(torrent, swarm, tid):
    # This thread should connect to a peer, or answer to a peer connection,
    # and provide with all the functionality needed to interact with it.
    # The PeerConnection object will help implementing the communication
    # protocol.
    #
    # The thread has to mantain connections with available peers, or wait
    # until more peers are available. Also, it has to request pieces to
    # the connected peer, save the piece and keep requesting free pieces
    # from the torrent file until the end.
    #
    # Also, the multiple causes of failure for the thread has to be
    # dealt with, updating the swarm.

    def newpeer():
        while True:
            peer = swarm.get_peer()
            pc = bittorrent.PeerConnection(torrent, peer)
            print '{0:4} Connecting with peer {1}:{2}'.format(tid, peer[0], peer[1])
            try:
                pc.connect()
            except bittorrent.DropConnection:
                continue
            break
        return pc

    pc = newpeer()

    while True:
        try:
            if pc.state == 'connected':
                if pc.me_interested == 0:
                    pc.send_interested()

            elif pc.state == 'ready':
                piece = pc.reserve_piece()
                if piece != None:
                    pc.request_piece()

            elif pc.state == 'downloading':
                if pc.has_piece():
                    if pc.submit_piece() == False:
                        pc.restart_piece()
                    else:
                        pc.reserve_piece()
                        pc.request_piece()

            message = pc.receive()
            if utils.config['verbose']:
                print '{0:4} [{1}] {2}'.format(tid, pc.state, bittorrent.msgtostr(*message))
        except bittorrent.DropConnection:
            pc.free_piece()
            pc = newpeer()

# Update status of the download on the screen. Called every 1 second by main().
def update_status(torrent, swarm):
    if utils.config['verbose'] == True:
        print 'Downloaded: %d/%d KiB @ %.2f KiB/s Swarm: %d'%(torrent.downloaded_bytes/1024, torrent.size/1024, torrent.rate, swarm.size())
        sys.stdout.flush()
    else:
        print '\rDownloaded: %d/%d KiB @ %.2f KiB/s Swarm: %d'%(torrent.downloaded_bytes/1024, torrent.size/1024, torrent.rate, swarm.size()),
        sys.stdout.flush()

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

    utils.generate_clientid()

    tracker = bittorrent.Tracker(torrent.data['announce'])
    tracker.update(torrent)

    swarm = bittorrent.Swarm()
    swarm.update_peers(tracker)

    threads = utils.config['threads']
    thread_list = []

    for i in range(threads):
        th = threading.Thread(target=peer_thread, args=(torrent, swarm, i))
        thread_list.append(th)
        th.start()

    while True:
        update_status(torrent, swarm)
        time.sleep(10)
        if tracker.update(torrent):
            update_peers(tracker)

if __name__=='__main__':
    main()
