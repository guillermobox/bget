import sys
import hashlib
import socket
import array

def parse_peers(string):
    def strtoport(string):
        import struct
        return int(str(struct.unpack('!H', string)[0]))

    peers = []
    while len(string) != 0:
        peer = string[0:6]
        string = string[6:]
        peers.append("%s:%d" % (socket.inet_ntoa(peer[0:4]), strtoport(peer[4:6])))
    return peers

def parse_list(string, offset):
    l = []
    while string[offset] != 'e':
        item, offset = parse_token(string, offset)
        l.append(item)
    return l, offset+1

def parse_dictionary(string, offset):
    d = {}
    while string[offset] != 'e':
        key, offset1 = parse_token(string, offset)
        value, offset2 = parse_token(string, offset1)
        offset = offset2
        if key == 'info':
            sha = hashlib.sha1(string[offset1:offset2])
            enc = sha.digest()
            print repr(enc)
            ret = ''
            for char in enc:
                if char in '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-_~':
                    ret += char
                else:
                    ret += '%' + '%02X'%ord(char)
            print ret
        elif key == 'peers':
            value = parse_peers(value)
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
    #if len(data) < 128:
    return data, offset+pos+1+length
    #else:
    #return 'data(%d)'%len(data), offset+pos+1+length

def parse_token(string, offset):
    if string[offset] == 'd':
        return parse_dictionary(string, offset+1)
    elif string[offset] == 'l':
        return parse_list(string, offset+1)
    elif string[offset] == 'i':
        return parse_integer(string, offset+1)
    else:
        return parse_data(string, offset)

if len(sys.argv) > 1:
    f = open(sys.argv[1])
else:
    f = sys.stdin

import pprint
pprint.pprint(parse_token(f.read(), 0)[0])
f.close()
