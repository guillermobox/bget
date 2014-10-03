import socket
import random
import os
import socket
import sys

def handshake():
    ret = ''
    ret += chr(19)
    ret += 'BitTorrent protocol'
    ret += '00000000'
    ret += "\x86\xb9\xf0T'\x9dMb\x7f\xffG\xb1\x100\t6E\xea\xdc\xa5"
    ret += '-AZ2060-'
    ret += os.urandom(12)
    return ret

def message(len, id, content):
    return len + id + content

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((sys.argv[1], int(sys.argv[2])))
s.send(handshake())
data = s.recv(1024)

s.send('000' + chr(13) + chr(6) + '0000' + '0000' + '000' + chr(255))
data = s.recv(1024)
print repr(data)
s.close()

