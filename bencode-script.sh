#!/usr/bin/env bash
curl http://torrent.fedoraproject.org:6969/announce?info_hash=%86%B9%F0T%27%9DMb%7F%FFG%B1%100%096E%EA%DC%A5 2>/dev/null | python bencode-parser.py

