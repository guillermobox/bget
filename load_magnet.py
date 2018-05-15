import urlparse
import sys

magnetlink = raw_input('Magnet link: ')

parsed = urlparse.urlparse(magnetlink)
components = urlparse.parse_qs(parsed.query)

print
print 'name: ' + components['dn'][0]
print 'trackers: '
for tracker in components['tr']:
    print '   ', tracker.strip()
print 'infohash: ' + components['xt'][0][9:]
print

