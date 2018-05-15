import tracker
import binascii
from torrent import Torrent
from tracker import TrackerException
import sys
import utils

torrent = Torrent(sys.argv[1])
utils.generate_clientid()

announces = set()
if 'announce-list' in torrent.data:
    announces.update(t[0] for t in torrent.data['announce-list'])
announces.add(torrent.data['announce'])

for trackerurl in announces:
    print trackerurl
    t = tracker.Tracker(trackerurl)
    try:
        t.update(torrent)
        print t.peerset
    except TrackerException as e:
        print e

