import getopt
import sys

from torrent import Torrent
from tracker import Tracker
from swarm import Swarm
from utils import configuration, generate_clientid


def usage():
    print 'Usage: bget [-i|--info] [-v|--verbose] [-t|--threads <numthreads>] <torrentpath|magnetlink>'
    print
    print 'Download the torrent defined by the path or magnet link.'
    print
    print '      -i,--info   Extract and print the information about the torrent.'
    print '   -v,--verbose   Show the protocol messages.'
    print '   -t,--threads   Use a maximum of <numthreads> threads to connect to peers. Has to be an int.'
    print
    exit(1)

def main():

    options, files = getopt.getopt(sys.argv[1:], 'ivt:', ['info', 'verbose', 'threads:'])

    for flag, value in options:
        if flag == '-v' or flag == '--verbose':
            configuration['verbose'] = True
        elif flag == '-t' or flag == '--threads':
            try:
                configuration['threads'] = int(value)
            except:
                usage()
        elif flag == '-i' or flag == '--info':
            configuration['info'] = True
        else:
            usage()

    if len(files) != 1:
        usage()

    try:
        torrent = Torrent(files[0])
    except:
        print 'Impossible to read torrent file/magnet link:', files[0]
        exit(1)

    if configuration['info'] == True:
        torrent.show()
        exit(0)

    torrent.start()

    generate_clientid()

    tracker = Tracker(torrent.data['announce'])
    tracker.update(torrent)

    swarm = Swarm()
    swarm.update_peers(tracker)

    threads = configuration['threads']

if __name__=='__main__':
    main()

