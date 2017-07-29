#!/bin/sh

export FLASK_DEBUG=1
export FLASK_APP="$1"
if [ "x$FLASK_APP" = "x" ]; then
    export FLASK_APP=nullbot.py
fi
python3 -m flask run --host=0.0.0.0
