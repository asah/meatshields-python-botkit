#!/usr/bin/env python3
# -*- compile-command: "/usr/local/bin/python3 sim.py" -*-

#---------------------------------------------------------------------------
# encoding/decoding for machine learning
#

import sys, datetime
import basicbot_lib as bblib

# reserve 0 for unknown terrain & units
TERRAIN_VALUES = dict( [(val,idx+1) for idx,val in enumerate(
    sorted(bblib.TERRAIN_DEFENSE.keys()))] )
UNIT_VALUES = dict( [(val,idx+4) for idx,val in enumerate(
    sorted(bblib.UNIT_TYPES.keys()))] )
UNIT_VALUES[None] = UNIT_VALUES[''] = 0
UNIT_VALUES['UnicornKnight'] = 1
UNIT_VALUES['UnicornArcher'] = 2
UNIT_VALUES['UnicornNinja'] = 3

MOVED_STATES = { None: 0, '0': 1, '1': 2 }

def append_unit_type_and_health(tile, done):
    if tile is None: tile = {}
    unit_type = tile.get('unit_name')
    if bblib.is_loaded_unicorn(tile):
        unit_type += tile['slot1_deployed_unit_name']
        # TODO: health of loaded unit
    bitmap = "{0:04b}".format(0 if done else UNIT_VALUES[unit_type])
    # 1-4=army_id, 5=empty
    bitmap += "{0:03b}".format(0 if done else int(tile.get('unit_army_id') or 4)+1)
    if 'unit_name' in tile and 'health' not in tile: tile['health'] = "100"
    health = tile.get('health')
    # 1=empty, 2-7=0-100% in 20% increments
    health_val = int(int(health if health else -20)/20)+2
    bitmap += "{0:03b}".format(0 if done else health_val)
    return bitmap

def encode_board_state(army_id_turn, resigned, game_info, tiles_list):
    bitmap = []
    bitmap += "{0:02b}".format(army_id_turn)  # up to 4 players
    for player_info in game_info['players'].values():
        army_id = player_info['army_id']
        bitmap += "{0:01b}".format(resigned[army_id])
        bitmap += "{0:06b}".format(min(int(player_info['funds'] / 1000), 63))  # funds: up to 63,000
        # TODO: augment with % fog?
        # TODO: augment with # towns/castles?
    
    for tile_idx in range(24 * 24):
        done = (tile_idx >= len(tiles_list))
        tile = {} if done else tiles_list[tile_idx]
        bitmap += "{0:05b}".format(0 if done else tile['x'])
        bitmap += "{0:05b}".format(0 if done else tile['y'])
        bitmap += "{0:04b}".format(0 if done else TERRAIN_VALUES[tile['terrain_name']])
        bitmap += "{0:02b}".format(0 if done else MOVED_STATES[tile.get('moved')])
        bitmap += append_unit_type_and_health(tile, done)
        # TODO: augment with # of visible enemies?
    return bitmap

NO_TILE = {'x':0, 'y':0}
def encode_move(move, tiles_by_idx):
    def emit_tile_loc(boolval, idx):
        tile = tiles_by_idx.get(idx, {'x':0, 'y':0}) if boolval else NO_TILE
        return "{0:05b}{0:05b}".format(tile['x'], tile['y'])
    def emit_bool(boolval):
        return '{0:01b}'.format(1 if boolval else 0)
    def append_bool(bitmap, skip, boolval):
        bitmap += 0 if skip else emit_bool(boolval)
        return bitmap, boolval
    
    data = move['data']
    bitmap, done = append_bool([], False, move.get('stop_worker_num', '') != '')
    bitmap, has_data = append_bool(bitmap, False, bool(move['data']))
    bitmap, end_turn = append_bool(bitmap, False, bool(data.get('end_turn', False)))
    bitmap, skip     = append_bool(bitmap, False, done or (not has_data))

    bitmap, has_purchase = append_bool(bitmap, skip, bool(data.get('purchase', False)))
    bitmap += '{0:01b}'.format(0 if skip else has_purchase)
    purchase = data['purchase'] if has_purchase else {}
    bitmap += "{0:04b}".format(UNIT_VALUES[purchase['unit_name']] if has_purchase else 0)
    bitmap += emit_tile_loc(has_purchase, bblib.movedict_xyidx(purchase))
    
    movemove = data.get('move', False)
    bitmap, has_move = append_bool(bitmap, skip, bool(movemove) and not skip)
    if not movemove: movemove = {'xCoordinate':-1,'yCoordinate':-1}
    # TODO: no movement?
    src_xyidx = bblib.movedict_xyidx(movemove)
    bitmap += emit_tile_loc(has_move, src_xyidx)
    bitmap, _            = append_bool(bitmap, skip, movemove.get('unit_action') == 'join')
    bitmap, _            = append_bool(bitmap, skip, movemove.get('unit_action') == 'load')
    bitmap, _            = append_bool(bitmap, skip, movemove.get('unit_action') == 'capture')
    bitmap, has_unload   = append_bool(bitmap, skip, movemove.get('unit_action') == 'unloadSlot1')
    action_xyidx = int(movemove.get('y_coord_action', -1))*1000 + \
                   int(movemove.get('x_coord_action', -1))
    bitmap += emit_tile_loc(has_unload, action_xyidx)
    bitmap, has_attack   = append_bool(bitmap, skip, 'x_coord_attack' in movemove)
    attack_xyidx = int(movemove.get('y_coord_attack', -1))*1000 + \
                   int(movemove.get('x_coord_attack', -1))
    bitmap += emit_tile_loc(has_unload, attack_xyidx)
    
    # augment with type & health of attacker & defender 
    bitmap += append_unit_type_and_health(tiles_by_idx.get(src_xyidx, {}), skip)
    bitmap += append_unit_type_and_health(tiles_by_idx.get(attack_xyidx, {}), skip)
    return bitmap

def write_board_move_state(winning_army_id_str, board_move_states):
    winning_army_id = int(winning_army_id_str)
    filename = 'board-{}.txt'.format(datetime.datetime.now().strftime('%Y%m%d%H%M%S%f'))
    fh = open(filename, 'w')
    for i, bitmap in enumerate(board_move_states):
        if i == 0:
            print('writing board state to {}: {} turns, {} bits each'.format(
                filename, len(board_move_states), len(bitmap)))
        bitmap_str = "".join(bitmap)
        army_id = int(bitmap_str[0:2], 2)
        fh.write("{}\t{}\n".format("1" if army_id == winning_army_id else "0", bitmap_str))
    fh.close()

def is_move_attack(board_move_state):
    return board_move_state[-MOVE_LEN:][45] == "1"

def is_move_capture(board_move_state):
    return board_move_state[-MOVE_LEN:][33] == "1"

MOVE_LEN = len(encode_move({'data':{'end_turn':True}}, {}))
EXAMPLE_ATTACK = encode_move({'data':{'move':{'x_coord_attack':0}}}, {})
assert(is_move_attack(EXAMPLE_ATTACK))
EXAMPLE_CAPTURE = encode_move({'data':{'move': {'unit_action':'capture'}}}, {})
assert(is_move_capture(EXAMPLE_CAPTURE))
# asah print(''.join(EXAMPLE_CAPTURE)) asah

if __name__ == '__main__':
    movetype = sys.argv[1]
    fh = sys.stdin if sys.argv[2] == '-' else open(sys.argv[2])
    for line in fh:
        line = line[0:-1]  # trim newline
        if (movetype == 'capture' and is_move_capture(line)) or \
           (movetype == 'attack' and is_move_attack(line)) or \
           False:
            print(line) 
