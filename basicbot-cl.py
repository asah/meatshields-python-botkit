#!/usr/bin/env python3
# pylint:disable=C0103

import basicbot_lib, json

def main():
    jsondata = json.loads(open('test_unicorn_load.json').read())
    player_id = str(jsondata['botPlayerId'])
    game_info = jsondata['gameInfo']
    print(basicbot_lib.select_next_move(player_id, game_info))

if __name__ == '__main__':
    main()
