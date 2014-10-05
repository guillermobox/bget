import sys
import hashlib
import math
import socket
import array
import pprint
import struct
import time
import collections
import urllib
import os
import random
import threading

MSG_CHOKE = '\x00'
MSG_UNCHOKE = '\x01'
MSG_INTERESTED = '\x02'
MSG_UNINTERESTED = '\x03'
MSG_HAVE = '\x04'
MSG_BITFIELD = '\x05'
MSG_REQUEST = '\x06'
MSG_PIECE = '\x07'
MSG_CANCEL = '\x08'

available_peers = set()
invalid_peers = set()
using_peers = set()
total_bytes = 0
downloaded_bytes = 0
download_rate = 0
peers = []
peer_connections = {}
peer_states = {}

def parse_list(string, offset):
    l = []
    while string[offset] != 'e':
        item, offset = parse_token(string, offset)
        l.append(item)
    return l, offset+1

def parse_dictionary(string, offset):
    d = collections.OrderedDict()
    while string[offset] != 'e':
        key, offset = parse_token(string, offset)
        value, offset = parse_token(string, offset)
        d[key] = value
    return d, offset+1

def parse_integer(string, offset):
    pos = string[offset:].index('e')
    if pos==-1:
        raise Exception()
    number = string[offset:offset+pos]
    return int(number), offset+pos+1

def parse_data(string, offset):
    pos = string[offset:].index(':')
    if pos==-1:
        raise Exception()
    length = int(string[offset:offset+pos])
    data = string[offset+pos+1:offset+pos+1+length]
    return data, offset+pos+1+length

def parse_token(string, offset):
    if string[offset] == 'd':
        return parse_dictionary(string, offset+1)
    elif string[offset] == 'l':
        return parse_list(string, offset+1)
    elif string[offset] == 'i':
        return parse_integer(string, offset+1)
    else:
        return parse_data(string, offset)

def bencoder(item):
    if type(item) in [collections.OrderedDict, dict]:
        payload = 'd'
        for key, value in item.iteritems():
            payload += bencoder(key)
            payload += bencoder(value)
        payload += 'e'
    elif type(item) == list:
        payload = 'l'
        for it in item:
            payload += bencoder(it)
        payload += 'e'
    elif type(item) == int:
        payload = 'i'
        payload += str(item)
        payload += 'e'
    elif type(item) == str:
        payload = str(len(item))+":"+item
    return payload

def bdecoder(string):
    return parse_token(string, 0)[0]

def parse_peers(string):
    def strtoport(string):
        return int(str(struct.unpack('!H', string)[0]))
    peers = []
    while len(string) != 0:
        peer = string[0:6]
        string = string[6:]
        peers.append({'ip':socket.inet_ntoa(peer[0:4]), 'port':strtoport(peer[4:6])})
    return peers

def read_tracker(url, infohash, clientid, size):
    url = url + '?info_hash=' + urllib.quote(infohash) + '&peer_id=' + urllib.quote(clientid) +'&port=6881' + '&event=started' + '&uploaded=0' + '&downloaded=0' + '&left=' + str(size) + '&compact=1'
    #print '  Downloading url:', url
    f = urllib.urlopen(url)
    data = f.read()
    f.close()
    try:
        return bdecoder(data)
    except:
        print 'Tracker answer is not a bencode document'
        print '\033[1;1m' + data + '\033[0m'
        return None

def update_peer_list(tracker):
    peers.extend(parse_peers(tracker['peers']))
    #peers = set(parse_peers(tracker['peers']))
    #available_peers.add(peers - invalid_peers)

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
        msg += struct.pack('!III', 0, kwargs['begin']*16384, 16384) #16384, 32768
    length = len(msg)
    return struct.pack('!I', length) + msg

def download_file(peerlist, infohash, clientid, torrent, tid):
    global downloaded_bytes
    piece = ''
    blockid = 0
    blockammount = 16
    peer_choked = 1
    me_interested = 0

    peer = random.choice(peerlist)
    peer_connections[tid] = peer['ip'] + ':' + str(peer['port'])

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((peer['ip'], peer['port']))
    except:
        exit(1)
    peer_states[tid] = 'Connected'
    s.send(handshake(infohash, clientid))
    hand = s.recv(68)
    if hand == '':
        peer_states[tid] = 'Handshake not returned!'
        exit(1)
    peer_states[tid] = 'Handshaked'
    s.send(create_message(MSG_INTERESTED))
    while True:
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
            s.send(create_message(MSG_REQUEST, begin=blockid))
        elif msgtype == MSG_PIECE:
            peer_states[tid] = 'Receiving data'
            data = s.recv(8)
            index, begin = struct.unpack('!II', data)
            length -= 8
            data = ''
            while length:
                input = s.recv(2048)
                length -= len(input)
                downloaded_bytes += length
                data += input
            piece += data
            blockid += 1
            if blockid == 16:
                peer_states[tid] = 'Piece finished'
                f = open('/tmp/test.bin', 'wb')
                f.write(piece)
                f.close()
                sha1 = hashlib.sha1(piece).digest()
                peer_states[tid] = 'Sha success'
                exit(0)
            else:
                s.send(create_message(MSG_REQUEST, begin=blockid))
        else:
            more = s.recv(length)

    return 0

def hashtostr(hash):
    return ''.join(map(lambda b: '%02x'%(ord(b),), hash))

if len(sys.argv) <= 1:
    print 'Provide a file name to download'
    exit(1)

f = open(sys.argv[1])
torrent = bdecoder(f.read())
f.close()

infohash = hashlib.sha1(bencoder(torrent['info'])).digest()

clientid = os.urandom(20)
total_length = 0

if 'length' in torrent['info']:
    print '  Single file torrent'
    print '   - (%d KiB) %s'%(torrent['info']['length']/1024, torrent['info']['name'])
    total_length = int(torrent['info']['length'])
else:
    print '  Multiple file torrent'
    for file in torrent['info']['files']:
        print '   - (%d KiB) %s'%(file['length']/1024, os.path.join(torrent['info']['name'], file['path'][0]))
        total_length += int(file['length'])

print '  Piece size: %d KiB'%(torrent['info']['piece length']/1024,)
print '  Pieces to download: %d'%(len(torrent['info']['pieces'])/20,)
print '  Creation date:', time.asctime(time.gmtime(int(torrent['creation date'])))
print '  Announce:', torrent['announce']
if 'comment' in torrent:
    print '  Comment:', torrent['comment']
print '  Client id: 0x' + hashtostr(clientid)
print '  Hash info: 0x' + hashtostr(infohash)

pammount = len(torrent['info']['pieces']) / 20
pieces = [0] * pammount
total_bytes = total_length

if False:
    tracker = read_tracker(torrent['announce'], infohash, clientid, total_length)
    if not tracker:
        exit(1)

    print '  Updating peer list'
    update_peer_list(tracker)
    print '  %d peers found'%(len(peers),)
    print

    import pickle
    f = open('/tmp/peers.pkl', 'w')
    pickle.dump(peers, f)
    f.close()
else:
    import pickle
    print '  Loading peers from pickle file'
    f = open('/tmp/peers.pkl', 'r')
    peers = pickle.load(f)
    f.close()

peer_connections[0] = 'None'
peer_states[0] = 'Not connected'
th = threading.Thread(target=download_file, args=(peers, infohash, clientid, torrent, 0))
th.start()

def update_status():
    percent = downloaded_bytes * 100.0 / total_bytes
    downloaded_chars = int(math.floor(percent * 80 / 100))
    left_chars = 80 - downloaded_chars
    print '\033[3A',
    print '\033[K %d] %s (%s)'%(0, peer_connections[0], peer_states[0])
    print '\033[K  %09d/%09d bytes downloaded (%3.2f %%)'%(downloaded_bytes, total_bytes, percent), time.asctime(time.localtime(time.time()))
    print '\033[K [' + '#' * downloaded_chars + ' ' * left_chars + ']'

while True:
    update_status()
    time.sleep(1)
