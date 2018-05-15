import binascii
import threading
import bencode
import hashlib
import os
import time

fileLock = threading.Lock()

class Torrent(object):
    def __init__(self, path):
        self.readtorrent(path)
        self.downloaded_bytes = 0
        self.downloaded_pieces = 0
        self.start_time = None
        self.last_time = None
        self.rate = 0
        self.bytes_uploaded = 0
        self.bytes_downloaded = 0
        self.bytes_left = 0

    def create_files(self):
        basepath = self.data['info']['name']
        files = []
        if 'files' in self.data['info']:
            for file in self.data['info']['files']:
                files.append( (file['path'][0], file['length']))
        else:
            files.append( (None, self.data['info']['length']))

        for file, len in files:
            if file:
                path = os.path.join(basepath, file)
            else:
                path = basepath
                basepath = '.'
            if not os.path.exists(basepath):
                os.makedirs(basepath)
            with open(path, 'w') as fh:
                fh.truncate(len)

    def start(self):
        self.create_files()

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
                    self.size += int(file['length'])
            self.numpieces = int(len(self.data['info']['pieces'])) / 20
            self.pieces = bytearray(self.numpieces)
            self.piecelength = int(self.data['info']['piece length'])
            self.bytes_left = self.size

    def register(self, bytes):
        self.downloaded_bytes += bytes
        self.bytes_left -= bytes
        self.bytes_downloaded += bytes

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

    def mappingpiece(self, index):
        ''' Return the mapping of the piece in the disc. This is,
        a list of (files, offsets and lengths) to write the content
        of the piece to the disc.'''
        mapping = []
        length = self.data['info']['piece length']
        offset = length * index
        searching = True

        if 'files' in self.data['info']:
            for file in self.data['info']['files']:
                if searching:
                    if offset >= file['length']:
                        offset -= file['length']
                    else:
                        searching = False

                if searching == False:
                    ammount = min(length, file['length'] - offset)
                    mapping.append( (file['path'][0], offset, ammount) )
                    length -= ammount
                    offset = 0
                    if length == 0:
                        break
        else:
            mapping.append( (None, offset, min(length, self.size - offset)))

        return mapping

    def writepiece(self, index, data):
        self.downloaded_pieces += 1

        map = self.mappingpiece(index)

        basepath = self.data['info']['name']

        for filepath, offset, length in map:
            if filepath:
                path = os.path.join(basepath, filepath)
            else:
                path = basepath
            datatowrite, data = data[:length], data[length:]
            with fileLock:
                with open(path, 'r+') as fh:
                    fh.seek(offset)
                    fh.write(datatowrite)

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
                print '   - (%8d B) %s'%(file['length'], os.path.join(info['name'], file['path'][0]))
        print '  Piece size: %d KiB'%(info['piece length']/1024,)
        print '  Pieces to download: %d'%(len(info['pieces'])/20,)
        print '  Creation date:', time.asctime(time.gmtime(int(self.data['creation date'])))
        if 'announce-list' in self.data:
            for ann in self.data['announce-list']:
                print '  Announce:', ann[0]
        else:
            print '  Announce:', self.data['announce']
        if 'comment' in self.data:
            print '  Comment:', self.data['comment']
        print '  Hash info: 0x' + binascii.hexlify(self.hash)
        print '='*80

