#!/usr/bin/env python3
# -*- compile-command: "/usr/local/bin/python3 sim.py" -*-

import json, copy, sys, os, time
import basicbot_lib as bblib, board_move_state as bms

DBG_GAME_STATE = (os.environ.get('DBG_GAME_STATE', '0') == '1')
DBG_MAX_TURNS = int(os.environ.get('DBG_MAX_TURNS', '350'))

MASTER_TILES_BY_IDX = None

BOARD_MOVE_STATES = []

def make_move(movenum, jsondata):
    """returns move"""
    player_id = str(jsondata['botPlayerId'])
    player_info = jsondata['gameInfo']['players'][player_id]
    army_id = player_info['army_id']
    if DBG_GAME_STATE:
        print("taking turn for player_id={}: funds={}".format(player_id, player_info['funds']))
    bblib.TILES_BY_IDX = copy.deepcopy(MASTER_TILES_BY_IDX)
    bblib.parse_tiles_by_idx(army_id, bblib.TILES_BY_IDX)
    bblib.set_fog_values(army_id, bblib.TILES_BY_IDX)
    jsondata['gameInfo']['__unitmap'] = bblib.unitmap_list(bblib.TILES_BY_IDX.values(), player_id)
    move = bblib.select_next_move(player_id, jsondata['gameInfo'], preparsed=True)
    #print("move #{}: \n{}".format(movenum, bblib.compact_json_dumps(move)))
    return move

def main():
    global MASTER_TILES_BY_IDX
    if os.environ.get('DBG_RAND_SEED', '') == '':
        bblib.DBG_RAND_SEED = int(time.time())
        print("randomizing random seed: {}".format(bblib.DBG_RAND_SEED))
    bblib.set_random_seed()
    game_state = json.loads(open('test_blank_board.json').read())
    game_info = game_state['gameInfo']
    bblib.parse_map(1, game_info['tiles'], game_info)
    MASTER_TILES_BY_IDX = copy.deepcopy(bblib.TILES_BY_IDX)
    game_info['__tilemap'] = bblib.tilemap_list(MASTER_TILES_BY_IDX.values())
    num_players = len(game_info['players'])
    last_move = {}
    player_info_dict = {}
    turns = {}
    resigned = {}
    position_scores = {}
    for player_info in game_info['players'].values():
        army_id = player_info['army_id']
        player_info['funds'] = 0
        last_move[army_id] = None
        player_info_dict[int(player_info['turn_order'])] = player_info
        turns[army_id] = []
        resigned[army_id] = False
        position_scores[army_id] = 0
    player_turn_idx = 0
    movenum = 0

    # main loop - take turn for each player
    while True:
        player_info = player_info_dict[player_turn_idx+1]
        army_id = player_info['army_id']
        if resigned[army_id]: continue
        bblib.initialize_player_turn(army_id, MASTER_TILES_BY_IDX, player_info, game_state)
        turns[army_id].append([])

        # take turn, which is multiple moves
        while True:
            if DBG_GAME_STATE:
                print("army_id={}  player_turn_idx={}  funds={}".format(
                    army_id, player_turn_idx+1, player_info['funds']))
            move = make_move(len(turns[army_id]), game_state)
            turns[army_id][-1].append(move)
            res = bblib.apply_move(army_id, MASTER_TILES_BY_IDX, player_info, move, dbg=True)
            bstate = bms.encode_board_state(player_turn_idx, resigned, game_info,
                                           list(MASTER_TILES_BY_IDX.values()))
            mstate = bms.encode_move(move, MASTER_TILES_BY_IDX)
# asah             if bms.is_move_capture(''.join(bstate + mstate)): asah
# asah                 print('capture found.') asah
            BOARD_MOVE_STATES.append(bstate + mstate)
            if not res:
                print("board_state={} bits: board={}, move={}".format(
                    len(bstate)+len(mstate), len(bstate), len(mstate)))
                break

        for aid in resigned.keys():
            owned = [tile for tile in MASTER_TILES_BY_IDX.values()
                     if tile['building_army_id'] == aid]
            print('army_id={} owns {} bldgs: {}'.format(aid, len(owned), " ".join([
                bblib.tilestr(mytile, show_unit=False) for mytile in owned])))

        if len(turns[army_id]) > DBG_MAX_TURNS:
            print("DBG_MAX_TURNS hit: ending game without resolution")
            sys.exit(0)
# asah             print("army #{} resigning: turns({}) > DBG_MAX_TURNS({})".format( asah
# asah                 army_id, len(turns[army_id]), DBG_MAX_TURNS)) asah
# asah             resigned[army_id] = True asah
            
        # resign if no moves in two turns
        if (len(turns[army_id]) > 1 and len(turns[army_id][-1]) == 1 and
            turns[army_id][-2][-1]['data']['end_turn']):
            print("army #{} resigning: no move in two turns".format(army_id))
            resigned[army_id] = True

        # resign if post-move, we're <75% the position-score of the next-lowest
        position_scores[army_id] = pscore = move['__score_pos']
        other_pscores = dict([item for item in position_scores.items()
                              if item[0] != army_id])
        if position_scores[army_id] < 0.70 * min(other_pscores.values()):
            print("army #{} resigning: pos_score={} vs others={}".format(
                army_id, pscore, other_pscores))
            resigned[army_id] = True

        # detect end of game
        if resigned[army_id] and sum(resigned.values()) == len(resigned)-1:
            for army_id, resigned in resigned.items():
                if not resigned:
                    print("winner: army_id={} (capital letters)".format(army_id))
                    print("final board position (no fog):")
                    tiles_list = MASTER_TILES_BY_IDX.values()
                    for final_tile in tiles_list:
                        final_tile['in_fog'] = '0'
                    print(bblib.unitmap_json(tiles_list, army_id))
                    bms.write_board_move_state(army_id, BOARD_MOVE_STATES)
                    sys.exit(0)

        # advance to next player
        player_turn_idx = (player_turn_idx + 1) % num_players

if __name__ == '__main__':
    main()
