#!/usr/bin/env python3
# -*- compile-command: "/usr/local/bin/python3 sim.py" -*-

#---------------------------------------------------------------------------
# encoding/decoding for machine learning
#

import sys, datetime, re, json, bz2
import basicbot_lib as bblib

# reserve 0 for unknown terrain & units
TERRAIN_VALUES = dict( [(val,idx+1) for idx,val in enumerate(
    sorted(bblib.TERRAIN_DEFENSE.keys()))] )
TERRAIN_VALUES['unknown'] = 0
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

def append_unit_type_and_health(tile, done):
    if tile is None: tile = {}
    unit_type = tile.get('unit_name')
    if bblib.is_loaded_unicorn(tile) or  bblib.is_loaded_skateboard(tile):
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

def encode_board_state(army_id_turn, resigned, game_info, tiles_list, dbg=False):
    def dbgbitmap(bitmap, msg, dbg=dbg):
        if dbg: print('bitmap loc {:4d} contains {}'.format(len(bitmap), msg))
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
    
    for tile_idx in range(24 * 24):
        done = (tile_idx >= len(tiles_list))
        tile = {} if done else tiles_list[tile_idx]
# asah         if tile_idx <= 1: dbgbitmap(bitmap, 'tile[x]={}'.format(0 if done else tile['x'])) asah
# asah         bitmap += "{0:05b}".format(0 if done else tile['x']) asah
# asah         if tile_idx <= 1: dbgbitmap(bitmap, 'tile[y]={}'.format(0 if done else tile['y'])) asah
# asah         bitmap += "{0:05b}".format(0 if done else tile['y']) asah
        if tile_idx <= 1: dbgbitmap(bitmap, 'terrain={}'.format(0 if done else tile['terrain_name']))
        bitmap += "{0:04b}".format(0 if done else TERRAIN_VALUES[tile['terrain_name']])
        if tile_idx <= 1: dbgbitmap(bitmap, 'moved')
        bitmap += "{0:02b}".format(0 if done else MOVED_STATES[tile.get('moved')])
        if tile_idx <= 1: dbgbitmap(bitmap, 'unit type and health')
        bitmap += append_unit_type_and_health(tile, done)
        # TODO: augment with # of visible enemies?
    return bitmap

NO_TILE = {'x':0, 'y':0}
def encode_move(move, tiles_by_idx, dbg=False):
    def emit_tile_loc(boolval, idx):
        tile = tiles_by_idx.get(idx, {'x':0, 'y':0}) if boolval else NO_TILE
        return "{0:05b}{0:05b}".format(tile['x'], tile['y'])
    def emit_bool(boolval):
        return '{0:01b}'.format(1 if boolval else 0)
    def append_bool(bitmap, skip, boolval):
        bitmap += 0 if skip else emit_bool(boolval)
        return bitmap, boolval
    def dbgbitmap(bitmap, msg, dbg=dbg):
        if dbg: print('bitmap loc {:4d} contains {}'.format(len(bitmap), msg))
    
    data = move['data']
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
    bitmap += "{0:04b}".format(UNIT_VALUES[purchase['unit_name']] if has_purchase else 0)
    dbgbitmap(bitmap, "purchase loc")
    bitmap += emit_tile_loc(has_purchase, bblib.movedict_xyidx(purchase))
    
    movemove = data.get('move', False)
    dbgbitmap(bitmap, "has_move")
    bitmap, has_move = append_bool(bitmap, skip, bool(movemove) and not skip)
    if not movemove: movemove = {'xCoordinate':-1,'yCoordinate':-1}
    # TODO: no movement?
    src_xyidx = bblib.movedict_xyidx(movemove)
    dbgbitmap(bitmap, "move src_loc")
    bitmap += emit_tile_loc(has_move, src_xyidx)
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
    bitmap += emit_tile_loc(has_unload, action_xyidx)
    dbgbitmap(bitmap, "is attack?")
    bitmap, has_attack   = append_bool(bitmap, skip, 'x_coord_attack' in movemove)
    attack_xyidx = int(movemove.get('y_coord_attack', -1))*1000 + \
                   int(movemove.get('x_coord_attack', -1))
    dbgbitmap(bitmap, "attack loc")
    bitmap += emit_tile_loc(has_unload, attack_xyidx)
    
    # augment with type & health of attacker & defender 
    dbgbitmap(bitmap, "attacker unit & health")
    bitmap += append_unit_type_and_health(tiles_by_idx.get(src_xyidx, {}), skip)
    dbgbitmap(bitmap, "defender unit & health")
    bitmap += append_unit_type_and_health(tiles_by_idx.get(attack_xyidx, {}), skip)
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

def is_move_attack(board_move_state):
    return board_move_state[-MOVE_LEN:][45] == "1"

def extract_tile_info(board_move_state, x, y):
    start_offset = 16 + x*26 + y*26*24
    # just return the terrain, moved, unit type and health
    return board_move_state[(start_offset+10):(start_offset+36)]

def restore_tile(board_move_state, x, y):
    """WIP"""
    state = extract_tile_info(board_move_state, x, y)
    chk_x, chk_y = int(state[0:5], 2), int(state[5:10], 2)
    tile = {
        'x': x, 'y': y, 'xyidx': x+y*1000,
        'terrain_name': TERRAIN_NAMES[int(state[10:14], 2)],
        'unit_name': UNIT_NAMES[int(state[16:20], 2)],
        'unit_army_id': int(state[20:23], 2),
        'health': int(state[23:26], 2),
    }
    tile['xystr'] = bblib.tile2xystr(tile)
    return tile

def extract_tile_xy(board_move_state, offset):
    return int(board_move_state[offset:offset+5], 2), int(board_move_state[offset+5:offset+10], 2)

def extract_attack_state(board_move_state):
    attack_x = int(board_move_state[-MOVE_LEN:][46:51], 2)
    attack_y = int(board_move_state[-MOVE_LEN:][51:55], 2)
    bblib.DBGPRINT('extract_attack_state:  attack: {},{}'.format(attack_x, attack_y))
    bitmap = board_move_state[-MOVE_LEN:][56:65]  # attacker info
    # TODO: only looks at +2/-2 from the defending tile, which misses
    # a lot for missile weapons, and also accidentally sees thru fog.
    for dx in range(-2,3):
        for dy in range(-2,3):
            if 0 <= attack_x+dx <= 23 and 0 <= attack_y+dy <= 23:
                bitmap += extract_tile_info(board_move_state, attack_x+dx, attack_y+dy)
    action_x, action_y = extract_tile_xy(board_move_state, 35)
    bblib.DBGPRINT('action: {},{}'.format(action_x, action_y))
    attacker = restore_tile(board_move_state, action_x, action_y)
    bblib.DBGPRINT('attacker: {}'.format(attacker))
    defender = restore_tile(board_move_state, attack_x, attack_y)
    bblib.DBGPRINT('defender: {}'.format(defender))
    damage = bblib.compute_damage(attacker, defender)
    bblib.DBGPRINT('damage: {}'.format(damage))
    return bitmap

def is_move_attack_json(state):
    return (state.get('move', {}) and \
            state.get('move', {}).get('data', {}) and \
            state.get('move', {}).get('data', {}).get('move', {}) and \
            state.get('move', {}).get('data', {}).get('move', {}).get('x_coord_attack') is not None)

def extract_attack_state_json(board_move_state, tiles_by_idx):
    movemove = board_move_state['move']['data']['move']
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
    if sys.argv[2] == '-':
        fh = sys.stdin
    elif 'bz2' in sys.argv[2]:
        fh = bz2.open(sys.argv[2], 'r')
    else:
        fh = open(sys.argv[2])
    if 'json' in movetype:
        board_game_states = json.loads(fh.read().decode())
        # legacy
        if len(board_game_states) == 1: board_game_states = board_game_states[0] 
        for state in board_game_states:
            tiles_by_idx = bblib.parse_map(state['army_id'], state['board']['tiles'],
                                           state['board'])
            print(bblib.combined_map(list(tiles_by_idx.values()), state['army_id']))
            if movetype == 'attack_state_json' and is_move_attack_json(state):
                print(extract_attack_state_json(state, tiles_by_idx))
                continue
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
