import random

class Swarm(object):
    def __init__(self):
        self.whitelist = set()
        self.blacklist = set()

    def update_peers(self, tracker):
        peers = tracker.peers()
        self.whitelist.update(peers - self.blacklist)

    def get_peer(self):
        if self.whitelist:
            peer = random.choice(tuple(self.whitelist))
            self.whitelist.remove(peer)
            self.blacklist.add(peer)
            return peer
        else:
            return None

    def size(self):
        return len(self.whitelist)

