#!/usr/bin/env python3

import basicbot_lib, json, copy

MASTER_TILES_BY_IDX = None

def take_turn(jsondata):
    """return True if game is to continue."""
    player_id = jsondata['botPlayerId']
    player_units = [tile for tile in MASTER_TILES_BY_IDX.values() if
                    tile.get('unit_name') is not None and tile['unit_army_id'] == player_id]
    player_info = jsondata['gameInfo']['players'][str(player_id)]
    player_info['funds'] = player_info.get('funds', 0) + (
        len([unit for unit in player_units if unit['terrain_name'] in CAPTURABLE_TERRAIN]))
    print("taking turn for player_id={}: funds={}".format(player_id, player_info['funds']))
    basicbot_lib.TILES_BY_IDX = copy.deepcopy(MASTER_TILES_BY_IDX)
    tiles_list = basicbot_lib.TILES_BY_IDX.values()
    for tile in tiles_list:
        tile['in_fog'] = "1"
        for unit in player_units:
            if basicbot_lib.is_visible(unit, tile):
                tile['in_fog'] = "0"
                break
        if tile['in_fog'] == "1":
            newtile = dict( (key, val) for key, val in tile.items() if key in [
                'xy', 'xystr', 'terrain_name', 'x_coordinate', 'y_coordinate', 'x', 'y',
                'defense', 'in_fog'])
            tile.clear()
            tile.update(newtile)
    jsondata['gameInfo']['__unitmap'] = basicbot_lib.unitmap_list(tiles_list, player_id)
    move = basicbot_lib.select_next_move(str(player_id), jsondata['gameInfo'], preparsed=True)
    print(move)

def main():
    global MASTER_TILES_BY_IDX
    jsondata = json.loads(open('test_blank_board.json').read())
    game_info = jsondata['gameInfo']
    basicbot_lib.parse_map(1, game_info['tiles'], game_info)
    MASTER_TILES_BY_IDX = copy.deepcopy(basicbot_lib.TILES_BY_IDX)
    game_info['__tilemap'] = basicbot_lib.tilemap_list(MASTER_TILES_BY_IDX.values())
    player_turn = 1
    num_players = len(game_info['players'])
    while True:
        for player_idstr, player_info in game_info['players'].items():
            if player_info['turn_order'] == str(player_turn):
                jsondata['botPlayerId'] = int(player_info['player_id'])
                if take_turn(jsondata) is False:
                    break
            player_turn = ((player_turn + 1) % num_players) + 1

if __name__ == '__main__':
    main()
