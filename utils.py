import os

clientid = None

# Configuration dictionary with default values. Some of this
# parameters can be changed from the command line.
configuration = dict(
        verbose=False,
        threads=1,
        info=False,
        blocksize=16384,
)

def generate_clientid():
    global clientid
    clientid = os.urandom(20)
