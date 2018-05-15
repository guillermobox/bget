import select
import socket
import struct
import threading

from utils import configuration

peerLock = threading.Lock()

MSG_CHOKE        = 0x00
MSG_UNCHOKE      = 0x01
MSG_INTERESTED   = 0x02
MSG_UNINTERESTED = 0x03
MSG_HAVE         = 0x04
MSG_BITFIELD     = 0x05
MSG_REQUEST      = 0x06
MSG_PIECE        = 0x07
MSG_CANCEL       = 0x08

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
        if configuration['verbose']:
            print 'Connected!'
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
            self.pieceoffset += configuration['blocksize']
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
        self.send(MSG_REQUEST, piece=self.piece, begin=self.pieceoffset, length=configuration['blocksize'])

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
        if configuration['verbose']:
            print 'Received handshake'
            print ' handshake >', hand[0:19]
            print '      mask >', '0x' + ''.join('%02x'%x for x in hand[20:28])
            print '  clientid >', '0x' + ''.join('%02x'%x for x in hand[29:])
        return True

    def handshake(self):
        if configuration['verbose']:
            print 'Sending handshake'
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
                        if pc.reserve_piece():
                            pc.request_piece()

            message = pc.receive()
            if configuration['verbose']:
                print '{0:4} [{1}] {2}'.format(tid, pc.state, bittorrent.msgtostr(*message))
        except bittorrent.DropConnection:
            if configuration['verbose']:
                print '{0:4} Dropped connection!'.format(tid)
            pc.free_piece()
            pc = newpeer()

