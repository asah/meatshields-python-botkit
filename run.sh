#!/bin/sh

if [ "x$FLASK_DEBUG" = "x" ]; then
    export FLASK_DEBUG=1
fi
export FLASK_APP="$1"
if [ "x$FLASK_APP" = "x" ]; then
    export FLASK_APP=basicbot.py
fi
if [ "x$PYBIN" = "x" ]; then
    export PYBIN="python3"
#    export PYBIN="./pypy3-v5.8.0-linux64/bin/pypy3 -X track-resources"
fi
$PYBIN -m flask run --host=0.0.0.0
