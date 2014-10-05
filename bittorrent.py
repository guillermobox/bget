import bencode
import hashlib
import os
import time
import utils
import urllib

class Torrent(object):
    def __init__(self, path):
        self.readfile(path)

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

    def writepiece(self, index, data):
        path = self.data['info']['name']
        piece_length = self.data['info']['piece length']
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
                compact     = 1)

        url = self.announce + '?' + urllib.urlencode(parameters)
        with urllib.urlopen(url) as fh:
            data = fh.read()

        try:
            self.data = bencode.decode(data)
            self.waittime = time.time() + int(self.data['interval'])
            return True
        except:
            return False

    def peers(self):
        peers = []
        data = tracker['peers']
        while len(data) != 0:
            peer = data[0:6]
            data = data[6:]
            ip = socket.inet_ntoa(peer[0:4])
            port = struct.unpack('!H', data[4:])[0]
            peers.append((ip, port))
        return peers
