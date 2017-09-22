#!/usr/bin/env python3
# -*- compile-command: "/usr/local/bin/python3 sim.py" -*-

#---------------------------------------------------------------------------
# encoding/decoding for machine learning
#

import sys, os, datetime, re, json, bz2, math
import basicbot_lib as bblib

DBG_MAX_UNITS = int(os.environ.get('DBG_MAX_UNITS', '75'))

# reserve 0 for unknown terrain & units
def mk_terrain_types():
    types = list(set(bblib.TERRAIN_DEFENSE.keys()) - bblib.CAPTURABLE_TERRAIN)
    for army_id in range(4):
        types += [name+str(army_id) for name in list(bblib.CAPTURABLE_TERRAIN)]
    return types

# sorting = reproducibility.  unknown==0, shouldn't happen
TERRAIN_VALUES = dict( [(val,idx) for idx,val in enumerate(['unknown'] + sorted(mk_terrain_types()))] )
TERRAIN_NAMES = dict( [(val,key) for key,val in TERRAIN_VALUES.items()] )
UNIT_VALUES = { None: 0, '': 0 }
for unit in sorted(bblib.UNIT_TYPES.keys()):
    UNIT_VALUES[unit] = len(UNIT_VALUES)
for carrier in ['Unicorn', 'Skateboard']:
    for unit in bblib.LOADABLE_UNITS:
        UNIT_VALUES[carrier+unit] = len(UNIT_VALUES)
if len(UNIT_VALUES) > 32: raise Exception('more than 32 UNIT_VALUES - update the code and delete the saved games.')

TERRAIN_NAMES = dict( [(val,key) for key,val in TERRAIN_VALUES.items()] )
UNIT_NAMES = dict( [(val,key) for key,val in UNIT_VALUES.items()] )

MOVED_STATES = { None: 0, '0': 1, '1': 2 }

def append_unit_info(tile, done):
    if tile is None: tile = {}
    unit_type = tile.get('unit_name')
    if bblib.is_loaded_unicorn(tile) or  bblib.is_loaded_skateboard(tile):
        unit_type += tile['slot1_deployed_unit_name']
        # TODO: health of loaded unit
    bitmap = "{0:05b}".format(0 if done else UNIT_VALUES[unit_type])
    # 1-4=army_id, 5=empty
    bitmap += "{0:03b}".format(0 if done else int(tile.get('unit_army_id') or 4)+1)
    if 'unit_name' in tile and 'health' not in tile: tile['health'] = "100"
    health = tile.get('health')
    # 1=empty, 2-7=0-100% in 20% increments
    health_val = int(int(health if health else -20)/20)+2
    bitmap += "{0:03b}".format(0 if done else health_val)
    return bitmap

def emit_tile_loc(tile):
    return "{0:05b}{0:05b}".format(tile['x'], tile['y'])

def emit_tile_terrain(tile):
    return "{0:05b}".format(0 if done else TERRAIN_VALUES[
            tile['terrain_name']+str(bblib.bldg_army_id(tile)) if
            tile['terrain_name'] in bblib.CAPTURABLE_TERRAIN else tile['terrain_name']])

def encode_board_state(army_id_turn, resigned, game_info, tiles_list, dbgloc=None):
    def dbgbitmap(bitmap, msg, dbgloc=dbgloc):
        if dbgloc is not None:
            print('bitmap loc {:4d} contains {}'.format(dbgloc+len(bitmap), msg))
    bitmap = []
    dbgbitmap(bitmap, 'army_id_turn')
    bitmap += "{0:02b}".format(army_id_turn)  # up to 4 players
    for player_info in game_info['players'].values():
        army_id = player_info['army_id']
        dbgbitmap(bitmap, 'resigned[army_id={}]'.format(army_id))
        bitmap += "{0:01b}".format(resigned[army_id])
        dbgbitmap(bitmap, 'funds[army_id={}]'.format(army_id))
        bitmap += "{0:06b}".format(min(int(int(player_info['funds']) / 1000), 63))  # funds: up to 63,000
        # TODO: augment with % fog?
        # TODO: augment with # towns/castles?

    bitmap_units = []
    for tile_idx in range(24 * 24):
        done = (tile_idx >= len(tiles_list))
        tile = {} if done else tiles_list[tile_idx]
        # note: don't write x/y coordinates
        if tile_idx <= 1: dbgbitmap(bitmap, 'terrain={}'.format(0 if done else tile['terrain_name']))
        bitmap += emit_tile_terrain(tile)
        if bblib.has_unit(tile):
            bitmap_unit = "{0:02b}".format(0 if done else MOVED_STATES[tile.get('moved')])
            bitmap_unit += append_unit_info(tile, done)
            bitmap_units.append(str(bitmap_unit))
    if len(bitmap_units) > DBG_MAX_UNITS:
        return None
    null_unit_bitmap = "00" + append_unit_info({}, True)
    for i in range(DBG_MAX_UNITS):
        if i < len(bitmap_units): dbgbitmap(bitmap, 'info for unit #{}'.format(i+1))
        bitmap += str(bitmap_units[i] if i < len(bitmap_units) else null_unit_bitmap)
        # TODO: augment with # of visible enemies?
    return bitmap

NO_TILE = {'x':0, 'y':0}
def encode_move(move, tiles_by_idx, dbgloc=None):
    def dbgbitmap(bitmap, msg, dbgloc=dbgloc):
        if dbgloc is not None:
            print('bitmap loc {:4d} (move idx {}) contains {}'.format(
                dbgloc+len(bitmap), len(bitmap), msg))
    def emit_tile_info(boolval, idx, tiles_by_idx=tiles_by_idx):
        tile = tiles_by_idx.get(idx, {'x':0, 'y':0}) if boolval else NO_TILE
        return emit_tile_loc(tile)
    def emit_bool(boolval):
        return '{0:01b}'.format(1 if boolval else 0)
    def append_bool(bitmap, skip, boolval):
        bitmap += 0 if skip else emit_bool(boolval)
        return bitmap, boolval
    
    data = move['data']
    dbgbitmap([], "stop_worker_num")
    bitmap, done = append_bool([], False, move.get('stop_worker_num', '') != '')
    dbgbitmap(bitmap, "move['data']")
    bitmap, has_data = append_bool(bitmap, False, bool(move['data']))
    dbgbitmap(bitmap, "end_turn")
    bitmap, end_turn = append_bool(bitmap, False, bool(data.get('end_turn', False)))
    dbgbitmap(bitmap, "has_data")
    bitmap, skip     = append_bool(bitmap, False, done or (not has_data))

    dbgbitmap(bitmap, "has_purchase")
    bitmap, has_purchase = append_bool(bitmap, skip, bool(data.get('purchase', False)))
    bitmap += '0'  # unused
    purchase = data['purchase'] if has_purchase else {}
    dbgbitmap(bitmap, "purchase unit_name")
    bitmap += "{0:05b}".format(UNIT_VALUES[purchase['unit_name']] if has_purchase else 0)
    dbgbitmap(bitmap, "purchase loc")
    bitmap += emit_tile_info(has_purchase, bblib.movedict_xyidx(purchase))
    
    movemove = data.get('move', False)
    dbgbitmap(bitmap, "has_move")
    bitmap, has_move = append_bool(bitmap, skip, bool(movemove) and not skip)
    if not movemove: movemove = {'xCoordinate':-1,'yCoordinate':-1}
    # TODO: no movement?
    src_xyidx = bblib.movedict_xyidx(movemove)
    dbgbitmap(bitmap, "move src_loc")
    bitmap += emit_tile_info(has_move, src_xyidx)
    dbgbitmap(bitmap, "is join?")
    bitmap, _            = append_bool(bitmap, skip, movemove.get('unit_action') == 'join')
    dbgbitmap(bitmap, "is load?")
    bitmap, _            = append_bool(bitmap, skip, movemove.get('unit_action') == 'load')
    dbgbitmap(bitmap, "is capture?")
    bitmap, _            = append_bool(bitmap, skip, movemove.get('unit_action') == 'capture')
    dbgbitmap(bitmap, "is unload?")
    bitmap, has_unload   = append_bool(bitmap, skip, movemove.get('unit_action') == 'unloadSlot1')
    action_xyidx = int(movemove.get('y_coord_action', -1))*1000 + \
                   int(movemove.get('x_coord_action', -1))
    dbgbitmap(bitmap, "action loc")
    bitmap += emit_tile_info(has_unload, action_xyidx)
    dbgbitmap(bitmap, "is attack?")
    bitmap, has_attack   = append_bool(bitmap, skip, 'x_coord_attack' in movemove)
    attack_xyidx = int(movemove.get('y_coord_attack', -1))*1000 + \
                   int(movemove.get('x_coord_attack', -1))
    dbgbitmap(bitmap, "attack loc")
    bitmap += emit_tile_info(has_unload, attack_xyidx)
    
    # augment with type & health of attacker & defender 
    dbgbitmap(bitmap, "attacker unit & health")
    bitmap += append_unit_info(tiles_by_idx.get(src_xyidx, {}), skip)
    dbgbitmap(bitmap, "defender unit & health")
    bitmap += append_unit_info(tiles_by_idx.get(attack_xyidx, {}), skip)
    return bitmap


def write_board_move_state(winning_army_id_str, board_move_states):
    winning_army_id = int(winning_army_id_str)
    filename = 'board-{}.txt.bz2'.format(datetime.datetime.now().strftime('%Y%m%d%H%M%S%f'))
    fh = bz2.open(filename, 'w')
    for i, bitmap in enumerate(board_move_states):
        if i == 0:
            print('writing board state to {}: {} moves, {} bits each'.format(
                filename, len(board_move_states), len(bitmap)))
        bitmap_str = "".join(bitmap)
        army_id = int(bitmap_str[0:2], 2)
        fh.write("{}\t{}\n".format("1" if army_id == winning_army_id else "0", bitmap_str)
                 .encode('utf-8'))
    fh.close()

def write_board_move_state_json(winning_army_id_str, board_move_states_json):
    winning_army_id = int(winning_army_id_str)
    filename = 'board-{}.json.bz2'.format(datetime.datetime.now().strftime('%Y%m%d%H%M%S%f'))
    fh = bz2.open(filename, 'w')
    maxlen = 0
    for i, jsondata in enumerate(board_move_states_json):
        jsondata['move_led_to_win'] = (1 if jsondata['army_id'] == winning_army_id else 0)
        maxlen = max(maxlen, len(json.dumps(jsondata)))
    print('writing board state to {}: {} moves, {} max bytes, {:.0f} avg bytes'.format(
        filename, len(board_move_states_json), maxlen,
        1.0*len(json.dumps(board_move_states_json))/len(board_move_states_json)))
    fh.write(json.dumps(board_move_states_json).encode('utf-8'))
    fh.close()

def is_move_attack(move):
    movemove = move.get('data', {}).get('move')
    return ('x_coord_attack' in movemove) if movemove else False

def encode_attack(move, tiles_by_idx, dbgloc=None):
    def dbgbitmap(bitmap, msg, dbgloc=dbgloc):
        if dbgloc is not None:
            print('bitmap loc {:4d} (move idx {}) contains {}'.format(
                dbgloc+len(bitmap), len(bitmap), msg))
    def emit_tile_info(boolval, idx, tiles_by_idx=tiles_by_idx):
        tile = tiles_by_idx.get(idx, {'x':0, 'y':0}) if boolval else NO_TILE
        return emit_tile_loc(tile)
    
    data = move['data']
    movemove = data['move']
    dbgbitmap(bitmap, "move src_loc")
    bitmap += emit_tile_info(has_move, src_xyidx)
    attack_xyidx = int(movemove.get('y_coord_attack', -1))*1000 + \
                   int(movemove.get('x_coord_attack', -1))
    dbgbitmap(bitmap, "attack loc")
    bitmap += emit_tile_info(has_unload, attack_xyidx)
    dbgbitmap(bitmap, "attacker unit & health")
    bitmap += append_unit_info(tiles_by_idx.get(src_xyidx, {}), skip)
    defender_x, defender_y = int(movemove['x_coord_attack']), int(movemove['y_coord_attack'])
    for dx in range(-2,3):
        for dy in range(-2,3):
            tile = tiles_by_idx.get(defender_x+dx + (defender_y+dy)*1000)
            tile = {} if tile is None else bblib.copy_tile_exc_loc(tile)
            bitmap += emit_tile_terrain(tile)
            bitmap += "{0:02b}".format(0 if done else MOVED_STATES[tile.get('moved')])
            bitmap += append_unit_info(tile, done)
    return bitmap
    

def extract_attack_state_json(board_move_state, tiles_by_idx):
    movemove = board_move_state['move']['data']['move']
    print('movemove: {}'.format(movemove))
    print('board_move_state: {}'.format(board_move_state['board']))
    res = {'attacker_neighbors': [], 'defender_neighbors': [], 'move': movemove}
    attacker = defender = None
    attacker_x, attacker_y = int(movemove['x_coordinate']), int(movemove['y_coordinate'])
    print('attacker: {},{}'.format(attacker_x, attacker_y))
    for dx in range(-2,3):
        for dy in range(-2,3):
            tile = tiles_by_idx.get(attacker_x+dx + (attacker_y+dy)*1000)
            tile = {} if tile is None else bblib.copy_tile_exc_loc(tile)
            if dx==0 and dy==0: attacker = tile
            res['attacker_neighbors'].append(tile)
            print('{}{}'.format('=> ' if dx==0 and dy==0 else '', bblib.tilestr(tile) if len(tile)>0 else ''))
    defender_x, defender_y = int(movemove['x_coord_attack']), int(movemove['y_coord_attack'])
    print('defender: {},{}'.format(defender_x, defender_y))
    for dx in range(-2,3):
        for dy in range(-2,3):
            tile = tiles_by_idx.get(defender_x+dx + (defender_y+dy)*1000)
            tile = {} if tile is None else bblib.copy_tile_exc_loc(tile)
            if dx==0 and dy==0: defender = tile
            res['defender_neighbors'].append(tile)
            print('{}{}'.format('=> ' if dx==0 and dy==0 else '', bblib.tilestr(tile) if len(tile)>0 else ''))
    print(attacker)
    print(defender)
    res['dmg20'] = 20 * int(bblib.compute_damage(attacker, defender) / 20)
    sys.exit(0)
    return res

if __name__ == '__main__':
    movetype = sys.argv[1]
    if sys.argv[2] == '-':
        fh = sys.stdin
    elif 'bz2' in sys.argv[2]:
        fh = bz2.open(sys.argv[2], 'r')
    else:
        fh = open(sys.argv[2])
    if re.search(r'json', movetype):
        board_game_states = json.loads(fh.read().decode())
        # legacy
        if len(board_game_states) == 1: board_game_states = board_game_states[0] 
        for state in board_game_states:
            tiles_by_idx = bblib.parse_map(state['army_id'], state['board']['tiles'],
                                           state['board'])
            if movetype == 'attack_state_json' and is_move_attack_json(state):
                print(extract_attack_state_json(state, tiles_by_idx))
            print(bblib.combined_map(list(tiles_by_idx.values()), state['army_id']))
        sys.exit(0)
            
    for line in fh:
        state = line[2:-1]  # trim newline
        print(restore_tile(state, 0,0))
        if movetype == 'attack_state' and is_move_attack(state):
            print(extract_attack_state(state))
            continue
        if (movetype == 'capture' and is_move_capture(state)) or \
           (movetype == 'attack' and is_move_attack(state)) or \
           False:
            print(state)
