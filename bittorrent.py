import bencode
import hashlib
import os
import random
import select
import socket
import struct
import threading
import time
import utils
import urllib

fileLock = threading.Lock()
peerLock = threading.Lock()

MSG_CHOKE        = '\x00'
MSG_UNCHOKE      = '\x01'
MSG_INTERESTED   = '\x02'
MSG_UNINTERESTED = '\x03'
MSG_HAVE         = '\x04'
MSG_BITFIELD     = '\x05'
MSG_REQUEST      = '\x06'
MSG_PIECE        = '\x07'
MSG_CANCEL       = '\x08'

class DropConnection(Exception):
    pass

def msgtostr(msg, mdata):
    msglist = 'choke unchoke interested uninterested have bitfield request piece cancel'.split()
    ret = ''
    if msg == None:
        return 'keep alive'
    msg = ord(msg)
    if msg < len(msglist):
        ret = msglist[msg]
        if chr(msg) == MSG_HAVE:
            index, = struct.unpack('!I', mdata)
            ret += ' piece {0}'.format(index)
        elif chr(msg) == MSG_BITFIELD:
            ret += ' length {0}'.format(len(mdata) * 8)
        elif chr(msg) == MSG_REQUEST:
            index, begin, length = struct.unpack('!III', mdata[0:12])
            ret += ' index {0} begin {1} length {2}'.format(index, begin, length)
        elif chr(msg) == MSG_PIECE:
            index, begin = struct.unpack('!II', mdata[0:8])
            ret += ' index {0} begin {1}'.format(index, begin)
        elif chr(msg) == MSG_CANCEL:
            index, begin, length = struct.unpack('!III', mdata[0:12])
            ret += ' index {0} begin {1} length {2}'.format(index, begin, length)
    else:
        ret = 'unknown message id ({0})'.format(msg)
    return ret

class Torrent(object):
    def __init__(self, path):
        self.readtorrent(path)
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

    def readtorrent(self, path):
        with open(path, 'r') as fh:
            data = fh.read()
            self.data = bencode.decode(data)
            info = bencode.encode(self.data['info'])
            self.hash = hashlib.sha1(info).digest()
            if 'length' in self.data['info']:
                self.size = int(self.data['info']['length'])
            else:
                self.size = 0
                for file in self.data['info']['files']:
                    self.size += file['length']
            self.numpieces = int(len(self.data['info']['pieces'])) / 20
            self.pieces = bytearray(self.numpieces)
            self.piecelength = int(self.data['info']['piece length'])

    def register(self, bytes):
        self.downloaded_bytes += bytes
        now = time.time()

        if self.start_time == None:
            self.start_time = now
        else:
            self.rate = self.downloaded_bytes / (1024 * (now - self.start_time))

        self.last_time = now

    def getpiece(self, piecelist):
        for i in xrange(len(self.pieces)):
            piece = self.pieces[i]
            have = piecelist[i]
            if have == 1 and piece == 0:
                self.pieces[i] = 1
                return i
        return None

    def freepiece(self, piece):
        self.pieces[piece] = 0

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
            print '   - (%8d KiB) %s'%(info['length']/1024, info['name'])
            total_length = int(info['length'])
        else:
            print '  Multiple file torrent'
            for file in info['files']:
                print '   - (%8d KiB) %s'%(file['length']/1024, os.path.join(info['name'], file['path'][0]))
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

    def update(self, torrent):
        if time.time() < self.waittime:
            return False

        parameters = dict(
                info_hash   = torrent.hash,
                peer_id     = utils.clientid,
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

class Swarm(object):
    def __init__(self):
        self.whitelist = set()
        self.blacklist = set()

    def update_peers(self, tracker):
        peers = tracker.peers()
        self.whitelist.update(peers - self.blacklist)

    def get_peer(self):
        if self.whitelist:
            peer = random.choice(tuple(self.whitelist))
            self.whitelist.remove(peer)
            self.blacklist.add(peer)
            return peer
        else:
            return None

    def size(self):
        return len(self.whitelist)

class PeerConnection(object):
    def __init__(self, torrent, peer):
        self.peer = peer
        self.torrent = torrent
        self.initial_state()

    def initial_state(self):
        self.me_choked = 0
        self.me_interested = 1
        self.peer_chocked = 1
        self.peer_interested = 0
        self.state = 'not-connected'
        self.piece = None
        self.piecebuffer = bytearray(self.torrent.piecelength)
        self.pieceoffset = 0
        self.have = bytearray(self.torrent.numpieces)

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(60)
        try:
            self.socket.connect(self.peer)
        except socket.timeout:
            raise DropConnection('Connection timed out')
        except socket.error:
            raise DropConnection('Connection refused')
        self.handshake()
        self.state = 'connected'
        self.send(MSG_INTERESTED)

    def process(self, message, data):
        if message == MSG_UNCHOKE:
            self.state = 'ready'
            self.peer_chocked = 0
        elif message == MSG_CHOKE:
            self.state = 'connected'
            self.peer_chocked = 1
        elif message == MSG_UNINTERESTED:
            self.peer_interested = 0
        elif message == MSG_INTERESTED:
            self.peer_interested = 1
        elif message == MSG_BITFIELD:
            byte2bits = lambda b: [(b>>i)&1 for i in xrange(7,-1,-1)]
            for n, byte in enumerate(data):
                bits = byte2bits(byte)
                self.have[n*8:(n+1)*8] = bits
        elif message == MSG_HAVE:
            piece, = struct.unpack('!I', data)
            self.have[piece] = 1
        elif message == MSG_PIECE:
            index, begin = struct.unpack('!II', data[0:8])
            data = data[8:]
            self.piecebuffer[begin:begin+len(data)] = data
            self.torrent.register(len(data))
            self.pieceoffset += utils.config['blocksize']
            if self.pieceoffset < self.torrent.piecelength:
                self.request_piece()

    def has_piece(self):
        if self.pieceoffset >= self.torrent.piecelength:
            return True
        return False

    def submit_piece(self):
        if self.torrent.checkpiece(self.piece, self.piecebuffer):
            self.torrent.writepiece(self.piece, self.piecebuffer)
            self.pieceoffset = 0
        else:
            return False

    def send_interested(self):
        self.send(MSG_INTERESTED)

    def request_piece(self):
        self.state = 'downloading'
        self.send(MSG_REQUEST, piece=self.piece, begin=self.pieceoffset, length=utils.config['blocksize'])

    def free_piece(self):
        self.state = 'ready'
        self.torrent.freepiece(self.piece)
        self.piece = None

    def reserve_piece(self):
        self.piece = self.torrent.getpiece(self.have)
        return self.piece

    def peer_percentage(self):
        pieces = sum(self.have)
        return 100.0 * pieces / (len(self.have))

    def checkhandshake(self, hand):
        return True

    def handshake(self):
        hand = struct.pack('!c19s8s20s20s',
                chr(19),
                'BitTorrent protocol',
                '\x00' * 8,
                self.torrent.hash,
                utils.clientid)
        self._send(hand)
        hand = self._receive(len(hand))
        return self.checkhandshake(hand)

    def _receive(self, bytes):
        payload = bytearray()
        while bytes:
            try:
                data = self.socket.recv(min(bytes, 1024))
            except socket.timeout:
                raise DropConnection('Connection timed out')
            except socket.error:
                raise DropConnection('Connection reset!')
            if not data:
                raise DropConnection('Peer disconnected')
            bytes -= len(data)
            payload.extend(data)
        return payload

    def receive(self):
        data = self._receive(4)
        length, = struct.unpack('!I', data)
        payload = self._receive(length)

        if length == 0:
            return None, None

        mtype, mdata = chr(payload[0]), payload[1:]
        self.process(mtype, mdata)
        return mtype, mdata

    def _send(self, bytes):
        length = len(bytes)
        while length:
            try:
                sent = self.socket.send(bytes)
            except socket.timeout:
                raise DropConnection('Connection timed out')
            length -= sent

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

