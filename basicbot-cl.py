#!/usr/bin/env python3
# pylint:disable=C0103

import os, json, random
import basicbot_lib as bblib

def main():
    jsondata = json.loads(open('test_scale.json').read())
    player_id = str(jsondata['botPlayerId'])
    game_info = jsondata['gameInfo']
    random.seed()
    #bblib.DBGPRINT = lambda msg: True
    move = bblib.select_next_move(player_id, game_info)
    print("move:\n{}".format(bblib.compact_json_dumps(move)))

if __name__ == '__main__':
    main()
