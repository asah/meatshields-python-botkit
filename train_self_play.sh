#!/bin/sh

platform=`uname`
if [[ $platform == 'linux' ]]; then
    ncores=`nproc --all`
    vm=pypy3-v5.8.0-linux64/bin/pypy3
elif [[ $platform == 'Darwin' ]]; then
    ncores=`sysctl hw.ncpu|awk '{print $2}'`
    vm=/usr/local/bin/python3
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

d=`date +%Y%m%d--%H%M%S`
while [ 1 ]; do $vm sim.py >> output-$d.txt ; done
