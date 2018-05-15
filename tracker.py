from urlparse import urlparse
import time
import urllib
import utils
import bencode
import socket
import struct

UDP_CONNECTION      = 0x41727101980
UDP_HANDSHAKE       = 0x00
UDP_ANNOUNCE        = 0x01
UDP_ERROR           = 0x03
UDP_EVENT_NONE      = 0x00
UDP_EVENT_COMPLETED = 0x01
UDP_EVENT_STARTED   = 0x02
UDP_EVENT_STOPPED   = 0x03

class TrackerException(Exception):
    pass

def Tracker(urlstr):
    url = urlparse(urlstr)

    if url.scheme.lower() in ['http', 'https']:
        return HTTPTracker(url)
    elif url.scheme.lower() in ['udp']:
        return UDPTracker(url)
    else:
        raise TrackerException('Unknown url for tracker')

class BaseTracker(object):
    def __init__(self, url):
        self.url = url
        self.waittime = time.time()
        self.peerset = set()

    def update_interval(self, interval):
        '''Update the interval with the value returned from tracker.'''
        self.waittime = time.time() + interval
        return

    def check_interval(self):
        '''Check if the interval has elapsed, so we can announce again.'''
        return time.time() > self.waittime

    def update(self, torrent):
        '''Empty announce to get peers.'''
        if not self.check_interval():
            return None

        peers = self.retrieve_peers(torrent)
        for peer in peers:
            self.peerset.add(peer)

    def announce_started(self, torrent):
        '''Announce that we started downloading the torrent.'''
        pass

    def announce_completed(self, torrent):
        '''Announce that we completed downloading the torrent.'''
        pass

    def announce_stopped(self, torrent):
        '''Announce that we stopped sharing the torrent.'''
        pass

class UDPTracker(BaseTracker):

    def is_connected(self):
        '''Check if we have a valid connection token.'''
        return self.connectionid and self.connectiontime + 120 < time.time()

    def sendrecv(self, sock, address, msg, length):
        '''Send the message to the address, via sock. Expected length answer.
        As per the specification, wait 15 * n seconds more after each try.'''
        self.transmissionid = 1
        timeout = 1
        n = 0

        while True:
            msgbody = msg()
            sock.settimeout(timeout)
            sock.sendto(msgbody, address)
            try:
                response, address = sock.recvfrom(length)
                break
            except socket.timeout:
                print 'Message timed out with timeout = {0}'.format(timeout)
                n += 1
                timeout = timeout + n * 15
                self.transmissionid += 1
                if n == 2:
                    raise TrackerException('Tracker unresponsive')

        action, responseid = struct.unpack('!II', response[:8])
        if action == UDP_ERROR:
            print 'UDP ERROR'
            raise TrackerException('UDP connection finished with error')
        if responseid != self.transmissionid:
            print 'TID error'
            raise TrackerException('UDP connection received unknown transmission id')

        return response

    def connect(self, sock, address):
        '''Connect to the tracker, updating the connection token.'''
        self.transmissionid = 1

        connection_msg = lambda: struct.pack('!qii',
                UDP_CONNECTION,
                UDP_HANDSHAKE,
                self.transmissionid)

        response = self.sendrecv(sock, address, connection_msg, 16)
        action, response_tid, connectionid = struct.unpack('!IIQ', response)

        self.connectiontime = time.time()
        self.connectionid = connectionid

    def retrieve_peers(self, torrent):

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.connectionid = None
        self.connectiontime = None

        url, sep, port = self.url.netloc.partition(':')
        port = int(port) if port else 6869
        address = (url, port)

        self.connect(sock, address)

        self.transmissionid += 1

        announce_msg = lambda: struct.pack('!QII20s20sQQQIIIIH',
                self.connectionid,
                UDP_ANNOUNCE,
                self.transmissionid,
                torrent.hash,
                utils.clientid,
                torrent.bytes_downloaded,
                torrent.bytes_left,
                torrent.bytes_uploaded,
                UDP_EVENT_NONE,
                0,
                0,
                10,
                6881
        )

        response = self.sendrecv(sock, address, announce_msg, 20 + 6*74)

        header, response = response[:20], response[20:]
        action, tid, interval, leechers, seeders = struct.unpack('!IIIII', header)
        if action == UDP_ERROR:
            raise TrackerException('UDP connection finished with error')

        total = leechers + seeders
        peers = set()
        for n in range(total):
            peer, response = response[:6], response[6:]
            print peer
            ip, port = struct.unpack('!IH', peer)
            peers.add((socket.inet_ntoa(peer[0:4]), port))

        sock.close()
        return peers

class HTTPTracker(BaseTracker):
    def retrieve_peers(self, torrent):
        parameters = dict(
                info_hash  = torrent.hash,
                peer_id    = utils.clientid,
                port       = 6881,
                event      = 'started',
                uploaded   = torrent.bytes_uploaded,
                downloaded = torrent.bytes_downloaded,
                left       = torrent.bytes_left,
                compact    = 1,
                numwant    = 10)

        url = '{0.scheme}://{0.netloc}{0.path}?{1}'.format(
                self.url,
                urllib.urlencode(parameters))

        try:
            fh = urllib.urlopen(url)
            data = fh.read()
            fh.close()
        except IOError as e:
            raise TrackerException('Impossible to open url')

        try:
            self.data = bencode.decode(data)
            if 'failure reason' in self.data:
                raise TrackerException('Failure when reading tracker: ' + self.data['failure reason'])
            if 'interval' in self.data:
                self.update_interval(int(self.data['interval']))
        except:
            raise TrackerException('Tracker response is not bencoded')

        peers = set()
        data = self.data['peers']
        while len(data) != 0:
            peer = data[0:6]
            data = data[6:]
            ip = socket.inet_ntoa(peer[0:4])
            port = struct.unpack('!H', peer[4:])[0]
            peers.add((ip, port))

        return peers

