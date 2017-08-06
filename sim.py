#!/usr/bin/env python3

import json, copy
import basicbot_lib as bblib

MASTER_TILES_BY_IDX = None

def take_turn(jsondata):
    """return True if game is to continue."""
    player_id = jsondata['botPlayerId']
    player_units = [tile for tile in MASTER_TILES_BY_IDX.values() if
                    tile.get('unit_name') is not None and tile['unit_army_id'] == player_id]
    player_info = jsondata['gameInfo']['players'][str(player_id)]
    player_info['funds'] = player_info.get('funds', 0) + (
        len([unit for unit in player_units if unit['terrain_name'] in bblib.CAPTURABLE_TERRAIN]))
    print("taking turn for player_id={}: funds={}".format(player_id, player_info['funds']))
    bblib.TILES_BY_IDX = copy.deepcopy(MASTER_TILES_BY_IDX)
    tiles_list = bblib.TILES_BY_IDX.values()
    for tile in tiles_list:
        tile['in_fog'] = "1"
        for unit in player_units:
            if bblib.is_visible(unit, tile):
                tile['in_fog'] = "0"
                break
        if tile['in_fog'] == "1":
            newtile = dict( (key, val) for key, val in tile.items() if key in [
                'xy', 'xystr', 'terrain_name', 'x_coordinate', 'y_coordinate', 'x', 'y',
                'defense', 'in_fog'])
            tile.clear()
            tile.update(newtile)
    jsondata['gameInfo']['__unitmap'] = bblib.unitmap_list(tiles_list, player_id)
    move = bblib.select_next_move(str(player_id), jsondata['gameInfo'], preparsed=True)
    print(move)

def main():
    global MASTER_TILES_BY_IDX
    jsondata = json.loads(open('test_blank_board.json').read())
    game_info = jsondata['gameInfo']
    bblib.parse_map(1, game_info['tiles'], game_info)
    MASTER_TILES_BY_IDX = copy.deepcopy(bblib.TILES_BY_IDX)
    game_info['__tilemap'] = bblib.tilemap_list(MASTER_TILES_BY_IDX.values())
    player_turn = 1
    num_players = len(game_info['players'])
    while True:
        for player_info in game_info['players'].values():
            if player_info['turn_order'] == str(player_turn):
                jsondata['botPlayerId'] = int(player_info['player_id'])
                if take_turn(jsondata) is False:
                    break
            player_turn = ((player_turn + 1) % num_players) + 1

if __name__ == '__main__':
    main()
