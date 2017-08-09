#!/usr/bin/env python3

import json, copy, random
import basicbot_lib as bblib

MASTER_TILES_BY_IDX = None

def take_turn(jsondata):
    """returns move"""
    player_id = jsondata['botPlayerId']
    player_info = jsondata['gameInfo']['players'][str(player_id)]
    player_info['funds'] = player_info.get('funds', 0) + \
                           bblib.new_funds(player_id, MASTER_TILES_BY_IDX)
    print("taking turn for player_id={}: funds={}".format(player_id, player_info['funds']))
    bblib.TILES_BY_IDX = copy.deepcopy(MASTER_TILES_BY_IDX)
    bblib.set_fog_values(player_id, bblib.TILES_BY_IDX)
    jsondata['gameInfo']['__unitmap'] = bblib.unitmap_list(bblib.TILES_BY_IDX.values(), player_id)
    random.seed()
    move = bblib.select_next_move(player_id, jsondata['gameInfo'], preparsed=True)
    print("move: \n{}".format(bblib.compact_json_dumps(move)))
    return move

def main():
    global MASTER_TILES_BY_IDX
    jsondata = json.loads(open('test_blank_board.json').read())
    game_info = jsondata['gameInfo']
    bblib.parse_map(1, game_info['tiles'], game_info)
    MASTER_TILES_BY_IDX = copy.deepcopy(bblib.TILES_BY_IDX)
    game_info['__tilemap'] = bblib.tilemap_list(MASTER_TILES_BY_IDX.values())
    player_turn_idx = 0
    num_players = len(game_info['players'])
    while True:
        for idx, player_info in enumerate(game_info['players'].values()):
            if str(player_turn_idx+1) == player_info['turn_order']:
                print("player_turn_idx: {}".format(player_turn_idx+1))
                player_id = jsondata['botPlayerId'] = int(player_info['player_id'])
                army_id = player_info.get(str(player_id), {}).get('army_id', '')
                while True:
                    move = take_turn(jsondata)
                    print(move)
                    if not bblib.apply_move(army_id, MASTER_TILES_BY_IDX, move):
                        break
            player_turn_idx = (player_turn_idx + 1) % num_players

if __name__ == '__main__':
    main()
