#!/bin/sh

wget https://bitbucket.org/pypy/pypy/downloads/pypy3-v5.8.0-linux64.tar.bz2
bunzip2 -c pypy3-v5.8.0-linux64.tar.bz2 |tar xf -
./pypy3-v5.8.0-linux64/bin/pypy3  -m ensurepip
./pypy3-v5.8.0-linux64/bin/pypy3 -mpip install -U wheel
./pypy3-v5.8.0-linux64/bin/pip3 install cython numpy

