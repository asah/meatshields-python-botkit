#!/bin/bash

JSON_FILE="$1"
if [ "x$JSON_FILE" = "x" ]; then
    JSON_FILE="example_getNextMove.json"
fi

curl -H "Content-Type: application/json" -X POST --data-ascii @$JSON_FILE http://localhost:5000/meatshields/bot/getNextMove
