#!/bin/sh

export FLASK_DEBUG=1
export FLASK_APP=ms1.py
python3 -m flask run --host=0.0.0.0
