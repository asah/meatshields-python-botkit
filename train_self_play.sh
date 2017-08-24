#!/bin/bash

platform=`uname`
if [[ $platform == 'Linux' ]]; then
    ncores=`nproc --all`
    vm=./pypy3-v5.8.0-linux64/bin/pypy3
elif [[ $platform == 'Darwin' ]]; then
    ncores=`sysctl hw.ncpu|awk '{print $2}'`
    vm=/usr/local/bin/python3
else
    echo "unknown platform: $platform"
    exit 1
fi

if [ "x$1" == "x" ]; then
    for core in $(seq 1 $ncores); do
	echo "launching $0 $core..."
	$0 $core &
	sleep 2
    done
    wait
    exit 0
fi

ts=`date +%Y%m%d--%H%M%S`
core=$1   # helps avoid filename conflicts
while [ 1 ]; do $vm sim.py >> output-$core-$ts.txt ; sleep 2; done
