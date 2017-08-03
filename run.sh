#!/bin/sh

if [ "x$FLASK_DEBUG" = "x" ]; then
    export FLASK_DEBUG=1
fi
export FLASK_APP="$1"
if [ "x$FLASK_APP" = "x" ]; then
    export FLASK_APP=basicbot.py
fi
python3 -m flask run --host=0.0.0.0
