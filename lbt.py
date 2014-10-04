import sys
import hashlib
import socket
import array
import pprint
import struct
import time
import collections
import urllib
import os
import random

MSG_CHOKE = '\x00'
MSG_UNCHOKE = '\x01'
MSG_INTERESTED = '\x02'
MSG_UNINTERESTED = '\x03'
MSG_HAVE = '\x04'
MSG_BITFIELD = '\x05'
MSG_REQUEST = '\x06'
MSG_PIECE = '\x07'
MSG_CANCEL = '\x08'

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
    print '  Downloading url:', url
    f = urllib.urlopen(url)
    data = f.read()
    f.close()
    try:
        return bdecoder(data)
    except:
        print 'Tracker answer is not a bencode document'
        print '\033[1;1m' + data + '\033[0m'
        return None

def get_peer_list(tracker):
    return parse_peers(tracker['peers'])

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
        msg += struct.pack('!III', 0, 0, 16384) #16384, 32768
    length = len(msg)
    return struct.pack('!I', length) + msg

def download_file(peerlist, infohash, clientid):
    peer_choked = 1
    me_interested = 0

    print 'Using random peer'
    peer = random.choice(peerlist)
    print 'Using peer: %s:%d'%(peer['ip'], peer['port'])
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((peer['ip'], peer['port']))
    except:
        print 'Wops! Connection refused!'
        exit(1)
    s.send(handshake(infohash, clientid))
    hand = s.recv(68)
    if hand == '':
        print 'Handshake not returned! How rude!'
        exit(1)
    print 'Handshake!', repr(hand)
    s.send(create_message(MSG_INTERESTED))
    while True:
        data = s.recv(4)
        if data=='':
            print 'Connection broken! Exiting'
            exit(1)
        length = struct.unpack('!I', data)[0]
        print 'Received length:', length
        if length == 0:
            print 'Keep-alive message! Everythings fine'
            continue
        msgtype = s.recv(1)
        length -= 1
        print 'Received data:', repr(msgtype)
        if msgtype == MSG_UNCHOKE:
            print 'Peer unchocked!'
            print 'Sending unchocke'
            s.send(create_message(MSG_UNCHOKE))
            print 'Sending interested'
            s.send(create_message(MSG_INTERESTED))
            print 'Sending request'
            s.send(create_message(MSG_REQUEST))
        elif msgtype == MSG_PIECE:
            print 'RECEVING A PIECE!'
            s.recv(8)
            length -= 8
            data = ''
            while length:
                input = s.recv(2048)
                length -= len(input)
                print 'Read %d bytes, %d up to go'%(len(input), length)
                data += input
            f = open('/tmp/test.bin', 'wb')
            f.write(data)
            f.close()
            print 'Block finished!'
        else:
            more = s.recv(length)

    return 0

def hashtostr(hash):
    return ''.join(map(lambda b: '%02X'%(ord(b),), hash))

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


tracker = read_tracker(torrent['announce'], infohash, clientid, total_length)
if not tracker:
    exit(1)
peers = get_peer_list(tracker)

#download_file([dict(ip='173.71.156.250', port=7002)], infohash, clientid)
#download_file([dict(ip='2.125.107.224', port=51413)], infohash, clientid)
download_file(peers, infohash, clientid)
