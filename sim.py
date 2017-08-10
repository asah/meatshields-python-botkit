#!/usr/bin/env python3

import json, copy, random, sys
import basicbot_lib as bblib

MASTER_TILES_BY_IDX = None

def take_turn(jsondata):
    """returns move"""
    player_id = str(jsondata['botPlayerId'])
    player_info = jsondata['gameInfo']['players'][player_id]
    army_id = player_info['army_id']
    player_info['funds'] = int(player_info.get('funds', 0)) + \
                           bblib.new_funds(army_id, MASTER_TILES_BY_IDX)
    print("taking turn for player_id={}: funds={}".format(player_id, player_info['funds']))
    bblib.TILES_BY_IDX = copy.deepcopy(MASTER_TILES_BY_IDX)
    bblib.parse_tiles_by_idx(army_id, bblib.TILES_BY_IDX)
    bblib.set_fog_values(army_id, bblib.TILES_BY_IDX)
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
    num_players = len(game_info['players'])
    last_move = {}
    player_info_dict = {}
    turns = {}
    resigned = {}
    for player_info in game_info['players'].values():
        army_id = player_info['army_id']
        last_move[army_id] = None
        player_info_dict[int(player_info['turn_order'])] = player_info
        turns[army_id] = []
        resigned[army_id] = False
    player_turn_idx = 0
    while True:
        player_info = player_info_dict[player_turn_idx+1]
        army_id = player_info['army_id']
        if resigned[army_id]: break
        turns[army_id].append([])
        player_id = jsondata['botPlayerId'] = int(player_info['player_id'])
        print("army_id={}  player_turn_idx={}".format(army_id, player_turn_idx+1))
        while True:
            move = take_turn(jsondata)
            turns[army_id][-1].append(move)
            if not bblib.apply_move(army_id, MASTER_TILES_BY_IDX, move):
                # TODO: other ways to win/lose
                if len(turns[army_id]) > 1 and len(turns[army_id][-1]) == 1:
                    if turns[army_id][-2][-1]['data']['end_turn']:
                        resigned[army_id] = True
                        if sum(resigned.values()) == len(resigned)-1:
                            for army_id, resigned in resigned.items():
                                if not resigned:
                                    print("winner: army_id={}".format(army_id))
                                    sys.exit(0)
                break
        player_turn_idx = (player_turn_idx + 1) % num_players

if __name__ == '__main__':
    main()
