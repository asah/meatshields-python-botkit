#!/bin/sh

export FLASK_DEBUG=1
export FLASK_APP=nullbot.py
python3 -m flask run --host=0.0.0.0
