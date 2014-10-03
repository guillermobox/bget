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
        peers.append("%s:%d" % (socket.inet_ntoa(peer[0:4]), strtoport(peer[4:6])))
    return peers

def read_tracker(url, infohash, clientid):
    f = urllib.urlopen(url + '?info_hash=' + urllib.quote(infohash) + '&port=6881')
    data = f.read()
    f.close()
    return bdecoder(data)

def get_peer_list(tracker):
    return parse_peers(tracker['peers'])
    
def download_file(peerlist, infohash, clientid):
    return 0

if len(sys.argv) <= 1:
    print 'Provide a file name to download'
    exit(1)

f = open(sys.argv[1])
torrent = bdecoder(f.read())
f.close()

infohash = hashlib.sha1(bencoder(torrent['info'])).digest()

clientid = os.urandom(20)

print 'Creation date:', time.asctime(time.gmtime(int(torrent['creation date'])))
print 'Announce:', torrent['announce']
print 'Client id: 0x' + ''.join(map(lambda b: '%02X'%(ord(b),), clientid))
print 'Hash info: 0x' + ''.join(map(lambda b: '%02X'%(ord(b),), infohash))

tracker = read_tracker(torrent['announce'], infohash, clientid)
peers = get_peer_list(tracker)
print sorted(peers)

download_file(peers, infohash, clientid)
