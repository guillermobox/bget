import bencode
import hashlib
import os
import select
import socket
import struct
import threading
import time
import utils
import urllib

fileLock = threading.Lock()

MSG_CHOKE        = '\x00'
MSG_UNCHOKE      = '\x01'
MSG_INTERESTED   = '\x02'
MSG_UNINTERESTED = '\x03'
MSG_HAVE         = '\x04'
MSG_BITFIELD     = '\x05'
MSG_REQUEST      = '\x06'
MSG_PIECE        = '\x07'
MSG_CANCEL       = '\x08'

def msgtostr(msg, mdata):
    msglist = 'choke unchoke interested uninterested have bitfield request piece cancel'.split()
    ret = ''
    msg = ord(msg)
    if msg < len(msglist):
        ret = msglist[msg]
        if chr(msg) == MSG_HAVE:
            piece, = struct.unpack('!I', mdata)
            ret += ' piece {0}'.format(piece)
        elif chr(msg) == MSG_BITFIELD:
            ret += ' length {0}'.format(len(mdata) * 8)
        elif chr(msg) == MSG_REQUEST:
            index, begin, length = struct.unpack('!III', mdata)
            ret += ' index {0} begin {1} length {2}'.format(index, begin, length)
        elif chr(msg) == MSG_PIECE:
            index, begin = stuct.unpack('!II', mdata[0:8])
            ret += ' index {0} begin {1}'.format(index, begin)
        elif chr(msg) == MSG_CANCEL:
            index, begin, length = struct.unpack('!III', mdata)
            ret += ' index {0} begin {1} length {2}'.format(index, begin, length)
    else:
        ret = 'unknown message id ({0})'.format(msg)
    return ret

class Torrent(object):
    def __init__(self, path):
        self.readfile(path)
        self.me_choked = 0
        self.me_interested = 1
        self.peer_chocked = 1
        self.peer_interested = 0
        self.downloaded_bytes = 0
        self.downloaded_pieces = 0
        self.start_time = None
        self.last_time = None
        self.rate = 0

    def start(self):
        path = self.data['info']['name']
        with open(path, 'w') as fh:
            length = int(self.data['info']['length'])
            fh.truncate(length)

    def readfile(self, path):
        with open(path, 'r') as fh:
            data = fh.read()
            self.data = bencode.decode(data)
            info = bencode.encode(self.data['info'])
            self.hash = hashlib.sha1(info).digest()
            self.size = int(self.data['info']['length'])
            pieces = int(len(self.data['info']['pieces'])) / 20
            self.pieces = [0] * pieces

    def register(self, bytes):
        self.downloaded_bytes += bytes
        now = time.time()

        if self.start_time == None:
            self.start_time = now
        else:
            self.rate = self.downloaded_bytes / (1024 * (now - self.start_time))

        self.last_time = now

    def checkpiece(self, index, data):
        sha1 = hashlib.sha1(data).digest()
        offset = index * 20
        expected = self.data['info']['pieces'][offset:offset+20]
        return sha1 == expected

    def writepiece(self, index, data):
        self.downloaded_pieces += 1
        path = self.data['info']['name']
        piece_length = self.data['info']['piece length']
        with fileLock:
            with open(path, 'r+') as fh:
                fh.seek(piece_length * index)
                fh.write(data)

    def show(self):
        info = self.data['info']
        print '='*80
        if 'length' in info:
            print '  Single file torrent'
            print '   - (%d KiB) %s'%(info['length']/1024, info['name'])
            total_length = int(info['length'])
        else:
            print '  Multiple file torrent'
            for file in info['files']:
                print '   - (%d KiB) %s'%(file['length']/1024, os.path.join(info['name'], file['path'][0]))
                total_length += int(file['length'])
        print '  Piece size: %d KiB'%(info['piece length']/1024,)
        print '  Pieces to download: %d'%(len(info['pieces'])/20,)
        print '  Creation date:', time.asctime(time.gmtime(int(self.data['creation date'])))
        print '  Announce:', self.data['announce']
        if 'comment' in self.data:
            print '  Comment:', self.data['comment']
        print '  Hash info: 0x' + utils.hashtostr(self.hash)
        print '='*80

class Tracker(object):
    def __init__(self, announce):
        self.announce = announce
        self.waittime = 0

    def get(self, torrent, clientid):
        if time.time() < self.waittime:
            return False

        parameters = dict(
                info_hash   = torrent.hash,
                peer_id     = clientid,
                port        = 6881,
                event       = 'started',
                uploaded    = 0,
                downloaded  = 0,
                left        = torrent.size,
                compact     = 1,
                numwant     = 100)

        url = self.announce + '?' + urllib.urlencode(parameters)
        fh = urllib.urlopen(url)
        data = fh.read()
        fh.close()

        try:
            self.data = bencode.decode(data)
            if 'interval' in self.data:
                self.waittime = time.time() + int(self.data['interval'])
            else:
                self.waittime = time.time() + 300
            return True
        except:
            return False

    def peers(self):
        peers = set()
        data = self.data['peers']
        while len(data) != 0:
            peer = data[0:6]
            data = data[6:]
            ip = socket.inet_ntoa(peer[0:4])
            port = struct.unpack('!H', peer[4:])[0]
            peers.add((ip, port))
        return peers

class PeerConnection(object):
    def __init__(self, peer):
        self.peer = peer
        self.state = 'Not connected'
        self.piece = -1
        self.last_download = None
        self.dropflag = False
        self.timetodie = 0

    def connect(self):
        self.state = 'Connecting'
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(10)
        self.socket.connect(self.peer)
        self.socket.settimeout(None)
        self.state = 'Connected'
        self.update_download()

    def is_stalled(self):
        if self.last_download:
            self.timetodie = 120 - (time.time() - self.last_download)
            return self.timetodie <= 0
        return False

    def update_download(self):
        self.last_download = time.time()

    def checkhandshake(self, hand):
        return True

    def handshake(self, torrent, clientid):
        hand = struct.pack('!c19s8s20s20s',
                chr(19),
                'BitTorrent protocol',
                '0' * 8,
                torrent.hash,
                clientid)
        self._send(hand)
        self.state = 'Handshake sent'
        hand = self._receive(len(hand))
        if hand == '':
            return False
        self.state = 'Handshake received'
        return self.checkhandshake(hand)

    def _receive(self, bytes):
        payload = bytearray()
        while bytes:
            self.socket.settimeout(5)
            data = self.socket.recv(min(bytes, 1024))
            bytes -= len(data)
            payload.extend(data)
            if self.dropflag == True:
                raise Exception('Dropped connection')
        return payload

    def receive(self):
        data = self._receive(4)
        length = struct.unpack('!I', data)[0]
        payload = self._receive(length)
        if length != 0:
            return chr(payload[0]), payload[1:]
        else:
            return None, None

    def _send(self, bytes):
        length = len(bytes)
        while length:
            self.socket.settimeout(5)
            sent = self.socket.send(bytes)
            length -= sent
            if self.dropflag == True:
                raise Exception('Dropped connection')

    def send(self, mtype, **kwargs):
        payload = bytearray()
        payload.extend(mtype)
        if mtype == MSG_REQUEST:
            payload.extend(struct.pack('!I', kwargs['piece']))
            payload.extend(struct.pack('!I', kwargs['begin']))
            payload.extend(struct.pack('!I', kwargs['length']))
        elif mtype == MSG_HAVE:
            payload.extend(struct.pack('!I', kwargs['piece']))
        length = len(payload)
        bytes = struct.pack('!I', length) + payload
        self._send(bytes)

    def drop(self):
        self.dropflag = True
