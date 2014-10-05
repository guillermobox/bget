import collections

def parse_list(string, offset):
    l = []
    while string[offset] != 'e':
        item, offset = parse_token(string, offset)
        l.append(item)
    return l, offset+1

def parse_dictionary(string, offset):
    d = collections.OrderedDict()
    while string[offset] != 'e':
        key, offset = parse_token(string, offset)
        value, offset = parse_token(string, offset)
        d[key] = value
    return d, offset+1

def parse_integer(string, offset):
    pos = string[offset:].index('e')
    if pos==-1:
        raise Exception()
    number = string[offset:offset+pos]
    return int(number), offset+pos+1

def parse_data(string, offset):
    pos = string[offset:].index(':')
    if pos==-1:
        raise Exception()
    length = int(string[offset:offset+pos])
    data = string[offset+pos+1:offset+pos+1+length]
    return data, offset+pos+1+length

def parse_token(string, offset):
    if string[offset] == 'd':
        return parse_dictionary(string, offset+1)
    elif string[offset] == 'l':
        return parse_list(string, offset+1)
    elif string[offset] == 'i':
        return parse_integer(string, offset+1)
    else:
        return parse_data(string, offset)

def encode(item):
    if type(item) in [collections.OrderedDict, dict]:
        payload = 'd'
        for key, value in item.iteritems():
            payload += encode(key)
            payload += encode(value)
        payload += 'e'
    elif type(item) == list:
        payload = 'l'
        for it in item:
            payload += encode(it)
        payload += 'e'
    elif type(item) == int:
        payload = 'i'
        payload += str(item)
        payload += 'e'
    elif type(item) == str:
        payload = str(len(item))+":"+item
    return payload

def decode(string):
    return parse_token(string, 0)[0]
