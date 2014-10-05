
def hashtostr(hash):
    return ''.join(map(lambda b: '%02x'%(ord(b),), hash))
