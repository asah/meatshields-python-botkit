#!/bin/sh

d=`date +%s`
while [ 1 ]; do pypy3-v5.8.0-linux64/bin/pypy3 sim.py >> output-$d.txt ; done
