config = dict(
        verbose=False,
        threads=1,
        info=False,
)

def hashtostr(hash):
    return ''.join(map(lambda b: '%02x'%(ord(b),), hash))
