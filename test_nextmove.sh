#!/bin/bash

curl -H "Content-Type: application/json" -X POST --data-ascii @example_getNextMove.json http://localhost:5000/meatshields/bot/getNextMove
