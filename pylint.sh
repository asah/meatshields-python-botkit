#!/bin/sh

PYTHONPATH=PYTHONPATH:$HOME/.local/lib/python3.5/site-packages pylint -r n *py | egrep -v '(TODO|maximum recursion)' 2>&1
