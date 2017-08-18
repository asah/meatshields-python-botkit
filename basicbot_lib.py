#!/usr/bin/env python3
# -*- compile-command: "/usr/local/bin/python3 sim.py" -*-
#
# pylint:disable=locally-disabled,fixme,bad-whitespace,missing-docstring,multiple-imports,global-statement,multiple-statements,no-self-use,too-few-public-methods,
#
# basicbot.py
#
# TODO list:
# - damage, healing ==> these are weighting/AI factors, not rules changes
# - joining
# - multiple enemies
#
# note: algorithm improvements are deferred for machine learning, for now just use random
#
import sys, os, re, copy, datetime, json, time, numpy, random
from multiprocessing import Process, Manager

DEBUG = (os.environ.get('FLASK_DEBUG', '0') == '1')

# use env vars to turn on verbose debugging -- more control and shuts up pylint
DBG_MOVEMENT = (os.environ.get('DBG_MOVEMENT', '0') == '1')
DBG_TIMING = (os.environ.get('DBG_TIMING', '0') == '1')
DBG_PARSE_TIMING = (os.environ.get('DBG_PARSE_TIMING', '0') == '1')
DBG_PRINT_SHORTCODES = (os.environ.get('DBG_PRINT_SHORTCODES', '0') == '1')
DBG_NOTABLE_TILES = (os.environ.get('DBG_NOTABLE_TILES', '0') == '1')
DBG_MOVES = (os.environ.get('DBG_MOVES', '0') == '1')
DBG_STATS = (os.environ.get('DBG_STATS', '1') == '1')
DBG_SCORING = (os.environ.get('DBG_SCORING', '0') == '1')
DBG_SCORING_DETAIL = (os.environ.get('DBG_SCORING_DETAIL', '0') == '1')
DBG_UNICORN_LOADING = (os.environ.get('DBG_UNICORN_LOADING', '0') == '1')
DBG_PRINT_DAMAGE_TBL = (os.environ.get('DBG_PRINT_DAMAGE_TBL', '0') == '1')
DBG_GAME_STATE = (os.environ.get('DBG_GAME_STATE', '0') == '1')
DBG_ATTACK = (os.environ.get('DBG_ATTACK', '0') == '1')

# pick from the top N moves - avoids herd of mediocre moves - 0 to pick all
PRUNE_TOP_N_MOVES = int(os.environ.get('PRUNE_TOP_N_MOVES', '6'))
if PRUNE_TOP_N_MOVES <= 0: PRUNE_TOP_N_MOVES = 99999

# max combined health before we no longer consider joining two units
# set to relatively high, so AI can uncover clever strategies
MAX_JOIN_THRESHOLD = int(os.environ.get('DBG_STATS', '150'))

PARALLEL_MOVE_DISCOVERY = (os.environ.get('PARALLEL_MOVE_DISCOVERY', '0') == '1')
DBG_PARALLEL_MOVE_DISCOVERY = (os.environ.get('DBG_PARALLEL_MOVE_DISCOVERY', '0') == '1')

APP = API = None

ATTACK_DEFENDER_KILLED = -1
ATTACK_ATTACKER_KILLED = -2

# remember turns and moves between API calls - helps debugging
GAMES = {}
LAST_MOVES = {}

def dbgprint(msg):
    print(msg)

DBGPRINT = dbgprint

def set_random_seed(val=1337):
    """reproducibility."""
    random.seed(val)
    numpy.random.seed(val)
    
def mkres(**args):
    """ e.g. mkres(move={"x_coordinates": ... }) """
    res = { 'purchase': False, 'end_turn': False, 'move': False }
    res.update(args)
    return { 'status': 'success', 'data': res }


# others are borders and ignored: Ocean, Reef
NORMAL_TERRAIN = set(['Plains','Town','Headquarters','Castle','Road','Bridge','Shore'])
WALKABLE_TERRAIN = set(list(NORMAL_TERRAIN) + ['Forest','Mountains','River'])
CAPTURABLE_TERRAIN = set(['Headquarters','Castle','Town'])
TERRAIN_DEFENSE = {
    'Mountains': 4,
    'Headquarters': 3, 'Town': 3, 'Castle': 3,
    'Forest': 2,
    'Plains': 1,
    'Shore': 0, 'Ocean': 0, 'Road': 0, 'River': 0, 'Bridge': 0, 'Reef': 0
}
TERRAIN_SHORTCODES = dict([(tkey, tkey[0]) for tkey in TERRAIN_DEFENSE.keys()])
TERRAIN_SHORTCODES['River'] = 'V'
TERRAIN_SHORTCODES['Reef'] = 'E'
UPPER_SHORTCODES_TERRAIN = dict([(tval,tkey) for tkey,tval in TERRAIN_SHORTCODES.items()])
LOWER_SHORTCODES_TERRAIN = dict([(tval.lower(),tkey) for tkey,tval in TERRAIN_SHORTCODES.items()])

UNIT_TYPES = {
    'Knight':       { 'cost':  1000, 'move': 3, 'vision': 2, 'atkmin': 1, 'atkmax': 1 },
    'Unicorn':      { 'cost':  1000, 'move': 4, 'vision': 1, 'atkmin': 0, 'atkmax': 0 },
    'Archer':       { 'cost':  2000, 'move': 2, 'vision': 2, 'atkmin': 2, 'atkmax': 3 },
    'Ninja':        { 'cost':  3000, 'move': 2, 'vision': 2, 'atkmin': 1, 'atkmax': 1 },
    'Mount':        { 'cost':  4000, 'move': 8, 'vision': 5, 'atkmin': 1, 'atkmax': 1 },
    'Boulder':      { 'cost':  6000, 'move': 5, 'vision': 1, 'atkmin': 2, 'atkmax': 3 },
    'Mage':         { 'cost':  6000, 'move': 6, 'vision': 3, 'atkmin': 1, 'atkmax': 1 },
    'Centaur':      { 'cost':  7000, 'move': 6, 'vision': 2, 'atkmin': 1, 'atkmax': 1 },
    'Brimstone':    { 'cost': 15000, 'move': 4, 'vision': 1, 'atkmin': 3, 'atkmax': 4 },
    'Troll':        { 'cost': 16000, 'move': 6, 'vision': 1, 'atkmin': 1, 'atkmax': 1 },
    'Giant':        { 'cost': 22000, 'move': 6, 'vision': 1, 'atkmin': 1, 'atkmax': 1 },
    'Thunderstorm': { 'cost': 28000, 'move': 4, 'vision': 1, 'atkmin': 3, 'atkmax': 5 },
}

UNIT_SHORTCODES = dict([(tkey, tkey[0]) for tkey in UNIT_TYPES.keys()])
UNIT_SHORTCODES.update({ 'Brimstone': 'R', 'Thunderstorm': 'H', 'Mage': 'E' })
UPPER_SHORTCODES_UNIT = dict([(tval,tkey) for tkey,tval in UNIT_SHORTCODES.items()])
LOWER_SHORTCODES_UNIT = dict([(tval.lower(),tkey) for tkey,tval in UNIT_SHORTCODES.items()])

LOADABLE_UNITS = CAPTURING_UNITS = set('Knight Archer Ninja'.split())
ATTACKING_UNITS = set([ukey for ukey,uval in UNIT_TYPES.items() if uval['atkmin'] > 0])
MISSILE_UNITS =   set([ukey for ukey,uval in UNIT_TYPES.items() if uval['atkmin'] > 1])
RETURNS_FIRE_UNITS = ATTACKING_UNITS - MISSILE_UNITS

DAMAGE_TBL = {}
ATTACK_STRENGTH = {}
DEFENSE_STRENGTH = {}
def setup_damage_table():
    dmg_matrix = [
        'Unicorn         1   1   1   1   1   1   1   1   1   1   1   1 ',
        'Knight         14  55  65  12  45   5  15   5  25   1  30   1 ',
        'Archer         40  45  55   7  20   4  15   5  35   4  45   4 ',
        'Mount          65  80  85  55  75   6  65   4  75   1  85   1 ',
        'Ninja          75  65  75  85  55  55  70  70  85  15  90  15 ',
        'Centaur        75  75  80  85  70  55  70  65  85  15 100  15 ',
        'Boulder        70  90  95  80  85  70  75  75  80  45  85  40 ',
        'Mage          120 120 120  85 120  30  75  35  85  20  95  10 ',
        'Brimstone      80  95 100  90  90  80  85  85  85  55  90  50 ',
        'Troll         105 105 115 105  95  85 105 105 105  55 115  45 ',
        'Thunderstorm  120 120 120 120 120  85 120  95 120  65 120  60 ',
        'Giant         125 125 135 125 115 105 115 115 125  75 135  55 '
    ]
    # first word is the unit type e.g. Unicorn - track the order these appear
    dmg_tbl_order = [re.sub(r'[: ].+', '', dmg.strip()) for dmg in dmg_matrix]
    num_types = len(dmg_tbl_order)
    for dmg_ar_str in dmg_matrix:
        dmg_ar = re.split(r' +', dmg_ar_str.strip().replace(':', ''))
        attacker = dmg_ar[0]
        DAMAGE_TBL[attacker] = {} # unit type
        for idx in range(len(dmg_ar)-1):
            defender = dmg_tbl_order[idx]
            DAMAGE_TBL[attacker][defender] = int(dmg_ar[idx+1])
            amt = int(dmg_ar[idx+1])
            ATTACK_STRENGTH[attacker] = ATTACK_STRENGTH.get(attacker, 0) + amt / num_types
            DEFENSE_STRENGTH[defender] = DEFENSE_STRENGTH.get(defender, 0) - amt / num_types
    min_attack = min(ATTACK_STRENGTH.values())
    min_defense = min(DEFENSE_STRENGTH.values())
    for unit in DAMAGE_TBL.keys():
        ATTACK_STRENGTH[unit] -= min_attack   # do allow 0: unicorns don't attack
        DEFENSE_STRENGTH[unit] -= min_defense - 10.0  # don't allow 0.0
    if DBG_PRINT_DAMAGE_TBL:
        new_sort = sorted(DAMAGE_TBL.keys(), key=lambda k: ATTACK_STRENGTH[k])
        new_tbl = []
        for attacker in new_sort:
            res = "{:12s} ".format(attacker)
            for defender in new_sort:
                res += ' {:3d}'.format(DAMAGE_TBL[attacker][defender])
            new_tbl.append(res)
        DBGPRINT("DAMAGE_TBL: {}\n{}\nATTACK_STRENGTH:{}\nDEFENSE_STRENGTH:{}\n".format(
            DAMAGE_TBL, "\n".join(new_tbl), ATTACK_STRENGTH, DEFENSE_STRENGTH))

setup_damage_table()

MY_HQ, OTHER_HQ = None, []
MY_UNITS, ENEMY_UNITS = [], []
MY_CASTLES, OTHER_CASTLES = [], []
MY_TOWNS, OTHER_TOWNS = [], []
TILES_BY_IDX = {}

TILE_DEFAULT_VALUES = dict([(tdv_fld,None) for tdv_fld in re.split(r'[ ,\r\n]+', """
  building_army_id, building_army_name, building_team_name, capture_remaining, 
  deployed_unit_id, primary_ammo, secondary_ammo, unit_id, unit_name, unit_team_name
  slot1_deployed_unit_health, slot1_deployed_unit_id, slot1_deployed_unit_name, 
  slot2_deployed_unit_id, unit_army_id, unit_army_name
""")])
TILE_DEFAULT_VALUES.update({
    'health': "100", "fuel": "100", "moved": "0"
})

TILE_KNOWN_FIELDS = list(TILE_DEFAULT_VALUES.keys()) + [
    'terrain_name', 'x_coordinate', 'y_coordinate', 'xy', 'xyidx', 'xystr'
]

def ifnone(val, default):
    return default if val is None else val

def ifdictnone(mydict, key, default):
    val = mydict.get(key, default)
    return default if val is None else val

def is_first_move_in_turn(game_id):
    last_move = LAST_MOVES.get(game_id)
    if last_move is None: return True # very first move!
    # if last_move is end_turn, then it's the 1st move of the next turn
    return last_move['data']['end_turn']

def tile2xystr(tile):
    """indexed from 0"""
    return "{:02d},{:02d}".format(tile['x'], tile['y'])

def sorted_tiles(tiles):
    return sorted(tiles, key=lambda tile: tile['xystr'])

def unit_health(unit):
    health = unit.get('health', 100)
    return 100 if health is None else int(health)

def compact_json_dumps(data):
    compact_response = json.dumps(data, indent=2, sort_keys=True)
    
    # keep curlies on the prev line
    compact_response = re.sub(r'(?m){\r?\n +', '{ ', compact_response)
    compact_response = re.sub(r'(?m)\r?\n +}', ' }', compact_response)
    
    # key sorting doesn't work nicely with x_coordinate/x_coord_attack
    if re.search(r'x_coord_attack', compact_response):
        compact_response = re.sub(
            r'(?m)("x_coordinate": "[0-9]+")([, \r\n]+)("y_coord_attack": [0-9]+)',
            r'\3\2\1', compact_response)

    # keep y-xxx on the same line as x---
    compact_response = re.sub(r'(?m)\r?\n +"([xy]Coord|[xy]_coord)', r' "\1', compact_response)
    # keep __unit_name on the same line as  __unit_action
    # keep building_army_name and building_team_name on the same line as building_army_id
    compact_response = re.sub(
        r'(?m)\r?\n +"(__(score|unit)_[_a-z]+|__walkcost|building_army_name|building_team_name|'+
        r'move|tile|health|secondary_ammo|unit_(army_name|id|name|team_name)|response_msec)',
        r' "\1', compact_response)
    return compact_response

def is_null_move(move):
    data = move['data']
    if data['end_turn']: return True
    if data['purchase']: return False
    movemove = data['move']
    if movemove:
        if 'x_coord_attack' in movemove: return False
        if movemove.get('unit_action') in ['load', 'unloadSlot1']: return False
        if len(movemove['movements']) == 0: return True
    DBGPRINT("unknown action: {}".format(move))
    return True             # shouldn't happen

def pathstr(path, show_terrain=False):
    if path is None: return "{}"
    if len(path) == 0: return "[]"
    return ("; " if show_terrain else ";").join([
        (("{}@{}".format(tile['terrain_name'][0:4], tile2xystr(tile)))
         if show_terrain else tile2xystr(tile)) for tile in path])

def tilestr(tile, show_details=False, show_unit=True):
    """canonical way to display a tile's location, terrain and (if present) unit.
    units are shortened to 3 chars, terrain to 4, which helps standardize formatting.
    army #1 units are printed is like this: unic  (for unicorn)
    army #2 units are printed is like this: Unic
    army #3 units are printed is like this: UNic
    army #4 units are printed is like this: UNIc
    army #5 units are printed is like this: UNIC.
    show_details=True is meant for one-line-per-tile output"""
    # TODO: show_details
    
    if tile.get('unit_name') in [None, ""]:
        unit_name = "----"
    else:
        unit_name = tile['unit_name'][0:4]
        if tile['unit_army_id'] != '1':
            army_id = int(tile['unit_army_id'])
            if army_id > 5:
                raise Exception("not implemented: more than 5 armies: {}".format(army_id))
            unit_name = unit_name[0:(army_id-2)].upper() + unit_name[(army_id-2):].lower()
    details = ""
    if show_details:
        details = " "+tile_details_str(tile)
    return "{}@{:02d},{:02d}{}{}".format(
        tile['terrain_name'][0:4], tile['x'], tile['y'], (":"+unit_name) if show_unit else "",
        details)

def movestr(move):
    data = move['data']
    if data['end_turn']: return 'end_turn'
    purchase = data['purchase']
    if purchase: return 'purch: {} @ {},{}'.format(
            purchase['unit_name'], purchase['x_coordinate'], purchase['y_coordinate'])
    movemove = data['move']
    if movemove:
        dest = movemove['movements'][-1] if len(movemove['movements']) > 0 else None
        if 'x_coord_attack' in movemove:
            postmove_action = " attack {},{}".format(
                movemove['x_coord_attack'], movemove['y_coord_attack'])
        elif movemove.get('unit_action') == "unloadSlot1":
            postmove_action = " unload to {},{}".format(
                movemove['x_coord_action'], movemove['y_coord_action'])
        else:
            postmove_action = ""
        return '{}: {} @ {},{} => {},{}{}'.format(
            movemove['__unit_action'], movemove['__unit_name'],
            movemove['x_coordinate'], movemove['y_coordinate'],
            dest['xCoordinate'] if dest else movemove['x_coordinate'],
            dest['yCoordinate'] if dest else movemove['y_coordinate'],
            postmove_action)
    return "unknown?!  {}".format(move)

def has_unit(tile):
    return (tile.get('unit_name', '') not in [None, ''])

def is_my_building(tile, army_id):
    return tile.get('building_army_id', '') == army_id

def can_capture(unit, tile, army_id):
    return (tile['terrain_name'] in CAPTURABLE_TERRAIN and unit['unit_name'] in CAPTURING_UNITS and
            not is_my_building(tile, army_id))

def get_capture_remaining(tile):
    return int(tile.get('capture_remaining') or 20)  # note: .get() can't return zero

def xy_nbrs(xyidx):
    # north/south aka y +/- 1000, east/west aka x +/- 1
    return [xyidx+1000, xyidx-1000, xyidx+1, xyidx-1]
    
def immed_nbrs(tile):
    """simple adjacency excluding tiles that are off the map."""
    return [nbr for nbr in [TILES_BY_IDX.get(xy) for xy in xy_nbrs(tile['xyidx'])]
            if nbr is not None]

def walk_cost(unit_type, terrain):
    if terrain not in WALKABLE_TERRAIN: return 0
    if unit_type == 'Knight':
        if terrain in NORMAL_TERRAIN: return 1
        else: return 2    # already checked for WALKABLE_TERRAIN
    elif unit_type in ['Archer','Ninja']:
        return 1          # already checked for WALKABLE_TERRAIN
    elif unit_type in ['Mount', 'Brimstone', 'Thunderstorm']:
        if terrain in ['Plains','Forest']: return 2
        elif terrain in NORMAL_TERRAIN: return 1
    else:
        if terrain == 'Forest': return 2
        elif terrain in NORMAL_TERRAIN: return 1
    # impassable
    return 0

def walkable_tiles(tile, army_id, unit_tile, cost_remaining, path):
    unit_type, terrain = unit_tile['unit_name'], tile['terrain_name']
    walkcost = walk_cost(unit_type, terrain)
    # impassable by this unit type, or beyond the range
    if walkcost == 0 or cost_remaining < walkcost: return []
    tile['seen'] = cost_remaining
    tile['path'] = path   # path to get to this tile
    dest_tiles = [tile]
    if DBG_MOVEMENT:
        DBGPRINT(('walkable_tiles(tile={}, unit_tile={}, walkcost={}, '+
                          'cost_remaining={}, path={}, typ={}, terr={}'
        ).format(tilestr(tile), tilestr(unit_tile), walkcost, cost_remaining,
                 pathstr(path), unit_type, terrain))
    immediate_neighbors = [nbr for nbr in immed_nbrs(tile) if
                           # revisit tiles only if there's greater walking range left
                           cost_remaining > nbr.get('seen', 0) and
                           # walk over friends but not enemies
                           nbr.get('unit_army_id') in [None, army_id]]
    if DBG_MOVEMENT:
        DBGPRINT('immediate neighbors of {}: {}, path:{}, moves left:{}'.format(
            tilestr(tile), pathstr(immediate_neighbors), pathstr(path),
            cost_remaining - walkcost))
    newpath = path + ([] if tile['xy'] == unit_tile['xy'] else [tile])
    for immediate_neighbor in immediate_neighbors:
        destinations = walkable_tiles(immediate_neighbor, army_id, unit_tile,
                                      cost_remaining - walkcost, newpath)
        msgs = ['neighbors of {}, newpath={}, destinations:'.format(
            tilestr(immediate_neighbor), pathstr(newpath))]
        for nbr in destinations:
            if nbr['path'] is None:
                nbr['path'] = newpath
            dest_tiles.append(nbr)
            msgs.append('{}: {}'.format(tilestr(nbr), pathstr(nbr['path'])))
        if DBG_MOVEMENT:
            DBGPRINT('\n'.join(msgs))
    if DBG_MOVEMENT:
        DBGPRINT('dest_tiles: {}'.format(";".join([tilestr(til) for til in dest_tiles])))
    return dest_tiles

def dist(unit, tile):
    """euclidean distance - used for missile attacks and a (bad) approximation of travel time."""
    return abs(tile['x'] - unit['x']) + abs(tile['y'] - unit['y'])

def max_travel(unit):
    return 6 if is_loaded_unicorn(unit) else unit['unit_type']['move']

def is_visible(unit, tile):
    distance = dist(unit, tile)
    if tile['terrain_name'] == 'Forest':
        return distance <= 1
    return (distance <= UNIT_TYPES[unit['unit_name']]['vision'])

def tile_dict_strip(mydict, other_fields_to_strip=None):
    fields_to_strip = [
        'primary_ammo','secondary_ammo','building_team_name','unit_army_name','defense',
        'building_army_name','deployed_unit_id','slot1_deployed_unit_id','slot2_deployed_unit_id',
        'tile_id','unit_id','unit_team_name','xyidx','x','y','x_coordinate','y_coordinate',
        'xy','xystr'
    ]
    if other_fields_to_strip is not None:
        fields_to_strip += other_fields_to_strip
    return dict([(k,v) for k,v in mydict.items() if v is not None and k not in fields_to_strip])

def compact_tile_in_place(tile):
    for fld in tile.keys():
        if fld not in TILE_KNOWN_FIELDS:
            del tile[fld]
    for fld, val in TILE_DEFAULT_VALUES.items():
        if tile.get(fld) == val:
            del tile[fld]
    tile['xy'] = tile['x_coordinate'] + "," + tile['y_coordinate']
    del tile['x_coordinate']
    del tile['y_coordinate']
    return tile
    
def compact_tile_in_place_json(tiles):
    new_tiles = copy.deepcopy(tiles)
    for tile_ar in new_tiles:
        for tile in tile_ar:
            compact_tile_in_place(tile)
    res = json.dumps(new_tiles)
    DBGPRINT(res)
    return res

def unitmap(tiles_list, army_id):
    """unit maps are less helpful than tile maps because there's fewer of them and
    they also have less than default (perfect) health.  But they're good for dev."""
    # array of strings
    len_x = max([tile['x'] for tile in tiles_list])
    len_y = max([tile['y'] for tile in tiles_list])
    text_map = [ [""] * (len_x+1) for _ in range(len_y+1)]
    for tile in tiles_list:
        xpos, ypos = tile['x'], tile['y']
        if tile.get('unit_name') is not None:
            mapchar = UNIT_SHORTCODES[tile['unit_name']]
            text_map[ypos][xpos] = (mapchar.upper() if tile['unit_army_id'] == army_id
                                    else mapchar.lower())
        else:
            text_map[ypos][xpos] = " "
    return text_map

def unitmap_list(tiles_list, army_id):
    return ["".join(line) for line in unitmap(tiles_list, army_id)]

def unitmap_json(tiles_list, army_id):
    res = "\n".join(['    "{}",'.format(line) for line in unitmap_list(tiles_list, army_id)])
    # strip trailing comma
    return res[0:-1]

def tilemap(tiles_list):
    # array of strings
    len_x = max([tile['x'] for tile in tiles_list])
    len_y = max([tile['y'] for tile in tiles_list])
    text_map = [ [""] * (len_x+1) for _ in range(len_y+1)]
    for tile in tiles_list:
        terrain_name = tile['terrain_name']
        mapchar = TERRAIN_SHORTCODES.get(terrain_name, "?:"+terrain_name)
        xpos, ypos = tile['x'], tile['y']
        text_map[ypos][xpos] = (mapchar.lower() if tile['in_fog'] == '1' else mapchar)
    return text_map

def tilemap_list(tiles_list):
    return ["".join(line) for line in tilemap(tiles_list)]

def tilemap_json(tiles_list):
    res = "\n".join(['    "{}",'.format(line) for line in tilemap_list(tiles_list)])
    # strip trailing comma
    return res[0:-1]

def combined_map(tiles_list, army_id):
    tlist, ulist = tilemap_list(tiles_list), unitmap_list(tiles_list, army_id)
    res = ""
    for i in range(len(tlist)):
        res += "{}  {}\n".format(ulist[i], tlist[i])
    return res

def movemap(tiles_list, army_id, turnmove):
    text_map = unitmap(tiles_list, army_id)
    if turnmove['data']['end_turn']: return text_map
    def set_text_map(tmap, xyitem, suffix, val):
        xpos = int(xyitem['x'+suffix])
        ypos = int(xyitem['y'+suffix])
        tmap[ypos][xpos] = val
        return tmap
    if turnmove['data']['purchase']:
        purch = turnmove['data']['purchase']
        return set_text_map(text_map, purch, '_coordinate', UNIT_SHORTCODES[purch['unit_name']])
    movemove = turnmove['data']['move']
    if 'x_coordinate' in movemove:
        for movement in movemove['movements']:
            set_text_map(text_map, movement, 'Coordinate', ".")
    if movemove.get('unit_action', '') == 'capture':
        if len(movemove['movements']) == 0:
            set_text_map(text_map, movemove, '_coordinate', "#")
        else:
            set_text_map(text_map, movemove['movements'][-1], 'Coordinate', "#")
    if 'x_coord_attack' in movemove:
        set_text_map(text_map, movemove, '_coord_attack', "x")
    return text_map

def movemap_list(tiles_list, army_id, turnmove):
    return ["".join(line) for line in movemap(tiles_list, army_id, turnmove)]

def movemap_json(tiles_list, army_id, turnmove):
    res = "\n".join(['    "{}",'.format(line) for line in
                     movemap_list(tiles_list, army_id, turnmove)])
    # strip trailing comma
    return res[0:-1]

def tile2xyidx(tile):
    return tile['y']*1000 + tile['x']

def idx2xy(xyidx):
    return int(xyidx / 1000), xyidx % 1000

def xyidxstr(xyidx):
    return "{},{}".format(xyidx % 1000, int(xyidx / 1000))

def set_xy_fields(tile):
    # support compact representation
    if 'xy' in tile:
        tile['x_coordinate'], tile['y_coordinate'] = tile['xy'].split(',')
    else:
        tile['xy'] = tile['x_coordinate'] + ',' + tile['y_coordinate']
    tile['x'], tile['y'] = int(tile['x_coordinate']), int(tile['y_coordinate'])
    tile['xystr'], tile['xyidx'] = tile2xystr(tile), tile2xyidx(tile)
    return tile

def parse_tiles_by_idx(army_id, tiles_by_idx):
    global MY_HQ, OTHER_HQ, MY_UNITS, ENEMY_UNITS, MY_CASTLES
    global OTHER_CASTLES, MY_TOWNS, OTHER_TOWNS
    MY_HQ, OTHER_HQ = None, []
    MY_UNITS, ENEMY_UNITS = [], []
    MY_CASTLES, OTHER_CASTLES = [], []
    MY_TOWNS, OTHER_TOWNS = [], []
    tiles, notable_tiles = list(tiles_by_idx.values()), []
    for tile in tiles:
        # unit_name will be absent if unit is killed...
        if tile.get('unit_name') is not None and tile['unit_army_id'] not in ["", None]:
            units_list = MY_UNITS if tile['unit_army_id'] == army_id else ENEMY_UNITS
            units_list.append(tile)
            tile['unit_type'] = UNIT_TYPES[tile['unit_name']]
            notable_tiles.append(tile)
        if tile['terrain_name'] == 'Headquarters':
            if is_my_building(tile, army_id):
                MY_HQ = tile
            else:
                OTHER_HQ.append(tile)
            notable_tiles.append(tile)
        elif tile['terrain_name'] == 'Castle':
            castle_list = MY_CASTLES if is_my_building(tile, army_id) else OTHER_CASTLES
            castle_list.append(tile)
            notable_tiles.append(tile)
        elif tile['terrain_name'] == 'Town':
            town_list = MY_TOWNS if is_my_building(tile, army_id) else OTHER_TOWNS
            town_list.append(tile)
    if DBG_NOTABLE_TILES:
        DBGPRINT("notable_tiles:  my army_id={}\n{}".format(
            army_id, "\n".join([tilestr(tile, show_details=True)
                                for tile in sorted_tiles(notable_tiles)])))
    
def parse_map(army_id, tiles, game_info):
    TILES_BY_IDX.clear()
    next_tile_id = 1000
    if '__tilemap' in game_info:
        for ypos, row in enumerate(game_info['__tilemap']):
            for xpos, char in enumerate(row):
                tile = set_xy_fields({
                    'in_fog': ("1" if char in LOWER_SHORTCODES_TERRAIN else "0"),
                    'terrain_name': UPPER_SHORTCODES_TERRAIN[char.upper()],
                    'x_coordinate': str(xpos), 'y_coordinate': str(ypos)
                })
                tile.update(dict((fld,val) for fld, val in TILE_DEFAULT_VALUES.items()
                                 if fld not in tile))
                tile['defense'] = TERRAIN_DEFENSE[tile['terrain_name']]
                tile['tile_id'] = next_tile_id
                next_tile_id += 1
                TILES_BY_IDX[tile['xyidx']] = tile
                #DBGPRINT('{}: {}'.format(tile['xy'], tile))
    # old style, including army details
    in_comment = False
    for tile_ar in tiles:
        for tile in tile_ar:
            if tile.get('__ignore_end') is not None:
                in_comment = False
                continue
            if tile.get('__ignore_start') is not None:
                in_comment = True
            if in_comment or tile.get('__comment') is not None: continue
            tile = set_xy_fields(tile)
            if '__tilemap' in game_info:
                if tile['xyidx'] not in TILES_BY_IDX:
                    raise Exception("bad tile index {} - tilemap doesn't match JSON?".format(
                        tile['xyidx']))
                TILES_BY_IDX[tile['xyidx']].update(tile)
            else:
                TILES_BY_IDX[tile['xyidx']] = tile
    parse_tiles_by_idx(army_id, TILES_BY_IDX)

def dist_from_enemy_hq(tile):
    return dist(OTHER_HQ[0], tile)

def name_val_dict_str(mydict):
    return " ".join([('{}={:3s}' if key in ['fuel','health'] else '{}={}').format(
        key,str(val)) for key,val in mydict.items()])

def tile_details_str(tile, extra_fields_to_exclude=None):
    fields_to_exclude = 'terrain_name unit_name unit_type'.split()
    if extra_fields_to_exclude:
        fields_to_exclude += extra_fields_to_exclude
    return name_val_dict_str(tile_dict_strip(tile, fields_to_exclude))

def units_by_dist(my_units, other_hq):
    # todo: support multiple enemies
    sorted_units = sorted(my_units, key=lambda tile: dist(other_hq, tile))
    if DBG_NOTABLE_TILES:
        dbg_units = ["units by distance:"]
        for unit in sorted_units:
            dbg_units.append("{}{}: {:.0f} from enemy hq [{},{}]: {}".format(
                "moved " if str(unit['moved'])=='1' else "", tilestr(unit),
                dist_from_enemy_hq(unit), other_hq['x'], other_hq['y'],
                tile_details_str(unit, ['moved'])))
        DBGPRINT("\n".join(dbg_units))
    return sorted_units

def my_units_by_dist():
    return units_by_dist(MY_UNITS, OTHER_HQ[0])

def msec(timedelta):
    return timedelta.seconds*1000 + int(timedelta.microseconds/1000)

def cache_move(res, moves):
    res_hash = json.dumps(res)
    if res_hash in moves:
        return False
    moves[res_hash] = res
    return True

def copy_move(move, update):
    new_move = copy.deepcopy(move)
    new_move.update(update)
    return new_move

def is_unloaded_unicorn(unit):
    return unit['unit_name'] == 'Unicorn' and \
        unit.get('slot1_deployed_unit_name', '') in [None, '']

def is_loaded_unicorn(unit):
    return unit['unit_name'] == 'Unicorn' and \
        unit.get('slot1_deployed_unit_name', '') not in [None, '']

def enumerate_moves(player_id, army_id, game_info, players, moves):
    my_info = players[player_id]
    # debug hack to force the algorithm to 'pick' this tile for the move,
    # building units at a castle, moving a unit, etc.
    dbg_force_tile = game_info.get('dbg_force_tile', '')   # x,y padded with zeroes, e.g. 04,14
    #todo: dbg_force_action = game_info.get('dbg_force_action', '')

    # unit movement, incl unicorn loading/unloading
    dbg_nbrs = []
    for unit in my_units_by_dist():
        unit['__mvclasses'] = {}
        if unit.get('dbg_force_tile') == True:
            dbg_force_tile = unit['xy']
    for unit in my_units_by_dist():
        if str(unit['moved'])=='1': continue
        if dbg_force_tile not in ['', unit['xy']]: continue
        unit_type = unit['unit_name']

        # decide on unicorn unloading first -- this makes it possible to unload/reload/move/unload
        # all in one turn
        if is_loaded_unicorn(unit):
            valid_neighbors = [nbr for nbr in immed_nbrs(unit) if nbr.get('unit_name') is None and
                               nbr['terrain_name'] in WALKABLE_TERRAIN]
            for nbr in valid_neighbors:
                unload_move = {
                    'x_coordinate': unit['x_coordinate'], 'y_coordinate': unit['y_coordinate'],
                    'x_coord_action': nbr['x_coordinate'], 'y_coord_action': nbr['y_coordinate'],
                    '__unit_name': unit['slot1_deployed_unit_name'], '__unit_action': 'unload',
                    'movements': [], 'unit_action': 'unloadSlot1' }
                if cache_move(mkres(move=unload_move), moves):
                    if DBG_UNICORN_LOADING:
                        DBGPRINT('loaded, unmoved unicorn: {} unload to {}'.format(
                            tilestr(unit), tilestr(nbr)))
                    return mkres(move=unload_move)

        # decide on unicorn (re)loading next -- possible unload/reload/move/unload all in one turn
        if is_unloaded_unicorn(unit):
            unicorn = unit
            for ldable in MY_UNITS:
                if ldable['moved'] == '1' or ldable['unit_name'] not in LOADABLE_UNITS: continue
                if dist(unicorn, ldable) > ldable['unit_type']['move']: continue
                if DBG_UNICORN_LOADING:
                    DBGPRINT('unloaded unicorn {}: checking loadable in range: {}'.format(
                        tilestr(unit), tilestr(ldable)))
                walk_dests = walkable_tiles(
                    ldable, army_id, ldable, ldable['unit_type']['move'], [])
                for walk_dest in walk_dests:
                    if unicorn['xy'] != walk_dest['xy']: continue
                    if DBG_UNICORN_LOADING:
                        DBGPRINT('walkdest: {} + {}'.format(
                            pathstr(walk_dest['path']), tilestr(walk_dest)))
                    walk_dest['path'].append(walk_dest)
                    if DBG_UNICORN_LOADING:
                        DBGPRINT('unloaded unicorn {}: {} walk to {} via {}'.format(
                            tilestr(unit), tilestr(ldable), tilestr(walk_dest),
                            pathstr(walk_dest['path'])))
                    load_move = {
                        'x_coordinate': ldable['x_coordinate'],
                        'y_coordinate': ldable['y_coordinate'],
                        '__unit_name': ldable['unit_name'], '__unit_action': 'load',
                        'unit_action': 'load', 'movements': [ {
                            "xCoordinate": p['x'], "yCoordinate": p['y'],
                            '__walkcost': walk_cost(ldable['unit_name'], p['terrain_name']),
                            '__terrain': p['terrain_name'] } for p in walk_dest['path'] ]}
                    if cache_move(mkres(move=load_move), moves):
                        if DBG_UNICORN_LOADING:
                            DBGPRINT('unloaded unicorn found: {} -- loading {} via {}'.format(
                                tilestr(unit), tilestr(ldable), pathstr(walk_dest['path'])))
                        return mkres(move=load_move)

        # moves
        for tile in TILES_BY_IDX.values():
            tile['seen'], tile['path'] = 0, None
        unit['seen'], unit['path'] = 1, []
        unit_max_move = max_travel(unit)
        neighbors = walkable_tiles(unit, army_id, unit, unit_max_move, [])
        # only include our own units if joinable
        neighbors = [nbr for nbr in neighbors if nbr.get('unit_army_id') is None or
                     (nbr.get('unit_army_id') == army_id and
                      nbr.get('unit_name') == unit['unit_name'] and
                      not is_loaded_unicorn(nbr) and not is_loaded_unicorn(unit) and
                      unit_health(nbr) + unit_health(unit) <= MAX_JOIN_THRESHOLD ) ]
        # not moving is a valid choice
        neighbors.append(unit)
        uniq_neighbors = {}
        for nbr in neighbors:
            nbr['pathstr'] = pathstr([nbr]+nbr['path'])
            uniq_neighbors[nbr['xystr']] = nbr

        dbg_nbrs.append("walkable neighbors of {}, move={}:".format(tilestr(unit), unit_max_move))
        for nbr in sorted_tiles(list(uniq_neighbors.values())):
            dbg_nbrs.append("{} via {}".format(
                tilestr(nbr), pathstr(nbr['path'], show_terrain=True)))
        if DBG_MOVEMENT:
            DBGPRINT("\n".join(dbg_nbrs))
            
        for dest in list(uniq_neighbors.values()):
            #DBGPRINT("checking src={} dest={}".format(tilestr(unit), tilestr(dest)))
            move = { 'x_coordinate': unit['x_coordinate'], 'y_coordinate': unit['y_coordinate'] }
            if dest['xy'] == unit['xy']:
                dbg_nbrs.append("no movement for {}, move={}:".format(
                    tilestr(unit), unit_max_move))
                move.update(
                    { '__unit_name': unit_type, '__unit_action': 'no_movement', 'movements': [] })
            else:
                move.update(
                    { '__unit_name': unit_type, '__unit_action': 'simple_movement',
                      '__unit_max_move': unit_max_move,
                      'movements': [ { "xCoordinate": p['x'], "yCoordinate": p['y'],
                                       '__walkcost': walk_cost(unit_type, p['terrain_name']),
                                       '__terrain': p['terrain_name'] }
                                     for p in (dest['path'] + [dest])] })

            # join units
            if (dest['xy'] != unit['xy'] and dest.get('unit_army_id') == army_id and
                dest['unit_name'] == unit['unit_name']):
                dbg_nbrs.append("join units for {}, move={}:".format(
                    tilestr(unit), unit_max_move))
                join_move = copy_move(move, {'unit_action': 'join', '__action': 'join'})
                if cache_move(mkres(move=join_move), moves): return mkres(move=join_move)
                # only join's are allowed on occupied tiles
                continue

            # capture open towns, castles and headquarters
            if can_capture(unit, dest, army_id):
                capture_move = copy_move(move, {'unit_action': 'capture', '__action': 'capture'})
                if cache_move(mkres(move=capture_move), moves): return mkres(move=capture_move)

            # unload unicorn after move
            if is_loaded_unicorn(unit):
                valid_neighbors = [nbr for nbr in immed_nbrs(dest) if
                                   nbr.get('unit_name') is None and
                                   nbr['terrain_name'] in WALKABLE_TERRAIN]
                for nbr in valid_neighbors:
                    unload_move = copy_move(move, {
                        'x_coord_action': nbr['x_coordinate'],
                        'y_coord_action': nbr['y_coordinate'],
                        '__unit_name': unit['slot1_deployed_unit_name'], '__unit_action': 'unload',
                        'unit_action': 'unloadSlot1' })
                    if cache_move(mkres(move=unload_move), moves):
                        if DBG_UNICORN_LOADING:
                            DBGPRINT('loaded, moved unicorn {} => {}, unload to {}'.format(
                                tilestr(unit), tilestr(dest), tilestr(nbr)))
                        return mkres(move=unload_move)
            
            # attacks
            if unit_type in ATTACKING_UNITS:
                # missile units: don't move, just attack
                attack_tile = unit if unit_type in MISSILE_UNITS else dest
                atkmin = unit['unit_type']['atkmin']
                atkmax = unit['unit_type']['atkmax']
                attack_neighbors = [enemy_unit for enemy_unit in ENEMY_UNITS
                                    if atkmin <= dist(attack_tile, enemy_unit) <= atkmax]
                if DBG_NOTABLE_TILES:
                    dbgmsgs = [ "enemy units from {}".format(tilestr(attack_tile)) ]
                    dbgmsgs.append("\n".join(["{}: {}".format(
                        dist(attack_tile, enemy_unit), tilestr(enemy_unit))
                                              for enemy_unit in ENEMY_UNITS]))
                    dbgmsgs.append("attack_neighbors for {}: {}".format(
                        tilestr(dest), "\n".join([pathstr(tile['path'])
                                                  for tile in attack_neighbors])))
                for attack_neighbor in attack_neighbors:
                    if DBG_NOTABLE_TILES:
                        dbgmsgs.append("- {}".format(tilestr(attack_neighbor, show_details=True)))
                    if attack_neighbor.get('unit_army_id', '') not in ['', None, army_id]:
                        if DBG_NOTABLE_TILES:
                            dbgmsgs.append("attacking: {}".format(tilestr(attack_neighbor)))
                        # missile units: don't move, just attack
                        attack_move = copy_move(move, {
                            'x_coord_attack': attack_neighbor['x'],
                            'y_coord_attack': attack_neighbor['y'] })
                        if unit_type in MISSILE_UNITS:
                            attack_move.update({ '__action': 'missile_attack', 'movements': [] })
                        else:
                            attack_move.update({ '__action': 'ground_attack' })
                        if cache_move(mkres(move=attack_move), moves):
                            if DBG_NOTABLE_TILES:
                                DBGPRINT("\n".join(dbgmsgs))
                            return mkres(move=attack_move)
            # simple moves
            if cache_move(mkres(move=move), moves):
                return mkres(move=move)

    # build new units at castles
    my_castles_by_dist = sorted(MY_CASTLES, key=dist_from_enemy_hq)
    if DBG_NOTABLE_TILES:
        dbg_castles = ["castles by distance:"]
        for castle in my_castles_by_dist:
            dbg_castles.append("{}: {:.1f} from enemy hq @{}".format(
                tilestr(castle, show_details=True), dist_from_enemy_hq(castle),
                tile2xystr(OTHER_HQ[0])))
        DBGPRINT("\n".join(dbg_castles))
    funds = int(my_info['funds'])
    for castle in my_castles_by_dist:
        if dbg_force_tile not in [None, '', castle['xy']]: continue
        if castle.get('unit_army_name') in [None, ''] and funds >= 1000:
            for purch_unit_name in [k for k,v in UNIT_TYPES.items() if v['cost'] <= funds]:
                res = mkres(purchase={
                    'x_coordinate': castle['x_coordinate'], 'y_coordinate': castle['y_coordinate'],
                    'unit_name': purch_unit_name })
                if cache_move(res, moves): return res

    # run out of possible moves
    if cache_move(mkres(end_turn=True), moves): return mkres(end_turn=True)
    return None

def enumerate_all_moves(player_id, army_id, game_info, players, compute_score=True,
                        result_queue=None, worker_num=None):
    #DBGPRINT("enumerate_all_moves({}, {}, {}, {}, {})\n\nTILES_BY_IDX: {}".format(
    #    player_id, army_id, game_info, players, result_queue, len(TILES_BY_IDX))
    next_move, moves = True, {}
    dbg_force_tile = game_info.get('dbg_force_tile', '')
    if DBG_MOVES and dbg_force_tile != '':
        DBGPRINT("dbg_force_tile: {}".format(dbg_force_tile))
    while next_move is not None:
        next_move = enumerate_moves(player_id, army_id, game_info, players, moves)
        #if next_move is not None: DBGPRINT('next_move: {}'.format(next_move))
    if result_queue is None:
        return moves
    if DBG_PARALLEL_MOVE_DISCOVERY:
        DBGPRINT('{} {} queuing {} moves'.format(worker_num, os.getpid(), len(moves)))
    retry_cnt = 0
    moves_list = list(moves.values()) + [ {'stop_worker_num': worker_num} ]
    for i, move in enumerate(moves_list):
        if compute_score and move.get('stop_worker_num', '') == '':
            move['__score'], move['__score_details'] = score_move(
                army_id, TILES_BY_IDX, players[player_id], move)
        move_json = json.dumps(move)
        while True:
            try:
                result_queue.put(move_json)
            except:
                retry_cnt += 1
                if DBG_PARALLEL_MOVE_DISCOVERY:
                    DBGPRINT('{} {} queue busy, sleeping and retrying {} bytes... {}'.format(
                        worker_num, os.getpid(), len(move_json), retry_cnt))
                time.sleep(1)
                continue
            else:
                retry_cnt = 0
                if DBG_PARALLEL_MOVE_DISCOVERY:
                    DBGPRINT('{} {} queued move #{} of {} - {}'.format(
                        worker_num, os.getpid(), i+1, len(moves_list),
                        len(move_json) if move.get('stop_worker_num') is None else 'STOP'))
                break
    if DBG_PARALLEL_MOVE_DISCOVERY:
        DBGPRINT('{} {} done queuing moves - returning.'.format(worker_num, os.getpid()))

def abbr_move_json(move):
    res = json.dumps(move, sort_keys=True)
    res = res.replace('{"status": "success", "data": {', '')
    res = res.replace(', "status": "success"}', '')
    res = re.sub(r'(, |{)"(purchase|end_turn|move)": false', '', res)
    res = re.sub(r'{?"(data|move)":[ {,]+', '', res)
    return res

def compressed_tile(tile):
    return dict( (fld,val) for fld,val in tile.items() if val is not None and
                 fld not in ['x','y','xyidx','xystr','x_coordinate','y_coordinate',
                             'path','seen','unit_type','defense','tile_id',
                             'terrain_name','in_fog'
                 ])

def compressed_game_info(game_info, army_id):
    """encoded as tilemap and interesting tiles"""
    game_info['__tilemap'] = tilemap_list(TILES_BY_IDX.values())
    game_info['__unitmap'] = unitmap_list(TILES_BY_IDX.values(), army_id)
    game_info['tiles'] = [[]]   # format is nested lists, but there's no meaning
    for tile in TILES_BY_IDX.values():
        tile = compressed_tile(tile)
        # skip tiles that are fully encoded by the tilemap
        if tile.keys() == set(['xy']):
            continue
        game_info['tiles'][0].append(tile)
    return game_info

def select_next_move(player_id, game_info, preparsed=False):
    """if preparsed, then TILES_BY_IDX is already set."""
    if DBG_PRINT_SHORTCODES:
        DBGPRINT("\n".join(["{}: {}".format(name, typ) for name, typ in
                            sorted(TERRAIN_SHORTCODES.items())]))
        DBGPRINT("\n".join(["{}: {}".format(name, typ) for name, typ in
                            sorted(UNIT_SHORTCODES.items())]))
    start_time = datetime.datetime.now()
    if DBG_PARSE_TIMING:
        parse_time = datetime.datetime.now() - start_time
        DBGPRINT('JSON parse time: {}'.format(msec(parse_time)))

    game_id = game_info['game_id']
    if game_id not in GAMES:
        GAMES[game_id] = { 'moves': [] }

    # save the request, for replay (low level debugging)
    game_info_json = ""
    if DEBUG:
        game_info_json = json.dumps(game_info, indent=2, sort_keys=True)
        lastreq_fh = open('lastreq.json', 'w')
        lastreq_fh.write('{} "botPlayerId": {}, "gameInfo": {} {}'.format(
            "{", player_id, game_info_json, "}"))
        lastreq_fh.close()

    tiles, players = game_info['tiles'], game_info['players']
    player_info = players[player_id]
    army_id = player_info['army_id']
    if not preparsed:
        parse_map(army_id, tiles, game_info)
    tiles_list = TILES_BY_IDX.values()
    if is_first_move_in_turn(game_info['game_id']):
        DBGPRINT("board:\n" + combined_map(tiles_list, army_id))
    unmoved_tiles = [unit for unit in (MY_UNITS + MY_CASTLES) if unit.get('moved') != '1']
    # don't parallelize end_turn
    if PARALLEL_MOVE_DISCOVERY and len(unmoved_tiles) > 0:
        mpmgr = Manager()
        moves, workers, result_queue = {}, [], mpmgr.Queue()
        # dbg_force_tile also signals a child process, i.e. avoid infinite recursion
        for unit in unmoved_tiles:
            if DBG_PARALLEL_MOVE_DISCOVERY:
                DBGPRINT("opening subprocess for unit: {}".format(tilestr(unit)))
            game_info['dbg_force_tile'] = unit['xy']
            worker = Process(target=enumerate_all_moves, args=(
                player_id, army_id, game_info, players, True, result_queue, len(workers), ))
            workers.append(worker)
            worker.start()
        if DBG_PARALLEL_MOVE_DISCOVERY:
            DBGPRINT("waiting for subprocesses...")
        cnt = 0
        while True:
            if DBG_PARALLEL_MOVE_DISCOVERY:
                DBGPRINT('main proc {}: queue size: {}, {} workers.  fetching item...'.format(
                    os.getpid(), result_queue.qsize(), sum([wrk is not None for wrk in workers])))
            try:
                qitem_json = result_queue.get_nowait()
            except:
                cnt += 1
                if DBG_PARALLEL_MOVE_DISCOVERY:
                    DBGPRINT('main proc {}: queue empty, {} workers, sleep/retry... {}'.format(
                        os.getpid(), sum([wrk is not None for wrk in workers]), cnt))
                time.sleep(1)
                continue
            cnt = 0
            qitem = json.loads(qitem_json)
            stop_worker_num = qitem.get('stop_worker_num')
            if stop_worker_num is None:
                cache_move(qitem, moves)
                continue
            if DBG_PARALLEL_MOVE_DISCOVERY:
                DBGPRINT("stopping worker {}".format(stop_worker_num))
            workers[stop_worker_num] = None
            if not any(workers):
                break
    else:
        moves = enumerate_all_moves(player_id, army_id, game_info, players)

    sum_scores = 0.0
    min_score = 999999999
    if len(moves) > 1:
        for mvkey in list(moves.keys()):
            if moves[mvkey]['data']['end_turn']:
                del moves[mvkey]
    for mvkey, move in moves.items():
        if '__score' not in move:
            move['__score'], move['__score_pos'], move['__score_details'] = score_move(
                army_id, TILES_BY_IDX, player_info, move)
        sum_scores += move['__score']
        min_score = min(min_score, move['__score'])
    sum_scores -= min_score * len(moves)
    sum_top_scores_wt = 0.0
    # pick from the top N moves, to avoid a herd of mediocre moves from competing
    top_moves = dict(sorted(moves.items(), key=lambda mv: mv[1]['__score'],
                            reverse=True)[0:PRUNE_TOP_N_MOVES])
    top_moves_keys = set(top_moves.keys())
    for mvkey, move in moves.items():
        # round is for pretty printing...
        move['__score_wt'] = 0.001 if sum_scores < 0.001 else \
                             round(max(0.0, (move['__score'] - min_score) / sum_scores), 4)
        if mvkey in top_moves_keys:
            sum_top_scores_wt += move['__score_wt']

    movekeys = list(top_moves.keys())
    mvkey = numpy.random.choice(   # pylint:disable=E1101
        movekeys, p=[top_moves[movekey]['__score_wt'] / sum_top_scores_wt for movekey in movekeys])
    if DBG_MOVES:
        sorted_moves = sorted(moves.keys(), key=lambda mvkey: moves[mvkey]['__score'],
                              reverse=True)
        DBGPRINT("{} moves available, choosing from top {}:\n{}".format(
            len(moves), PRUNE_TOP_N_MOVES, "\n".join(["{}{}".format(
                ("=> " if mvkey == key else ""), abbr_move_json(moves[key])
                ) for key in sorted_moves])
        ))
    if len(moves) == 1:
        DBGPRINT("board:\n" + combined_map(tiles_list, army_id))
    move = moves[mvkey]

    # save the game, for debugging
    if DEBUG:
        game_info_json = compact_json_dumps(compressed_game_info(game_info, army_id))
        game_fh = open('game-{}.json'.format(game_id), 'w')
        game_fh.write('{} "botPlayerId": {}, "gameInfo": {} {}'.format(
            "{", player_id, game_info_json, "}"))
        game_fh.close()

    LAST_MOVES[game_id] = move
    total_time = datetime.datetime.now() - start_time
    if DBG_TIMING:
        DBGPRINT('total response time: {}'.format(msec(total_time)))
    # compact response helps debugging
    move['__maps'] = { 'move': movemap_list(tiles_list, army_id, move),
                       'tile': tilemap_list(tiles_list) }
    move['__stats'] = { 'possible_moves': len(moves),
                        'response_msec': msec(total_time) }
    return move

def player_units(army_id, tiles_by_idx):
    return [tile for tile in tiles_by_idx.values() if tile.get('unit_army_id') == army_id]
            
def player_bldgs(army_id, tiles_by_idx):
    return [tile for tile in tiles_by_idx.values() if tile.get('building_army_id') == army_id]

def set_fog_values(army_id, tiles_by_idx):
    my_units = player_units(army_id, tiles_by_idx)
    my_bldgs = player_bldgs(army_id, tiles_by_idx)
    num_visible = 0
    for tile in tiles_by_idx.values():
        tile['in_fog'] = "1"
        for unit in my_units:
            if is_visible(unit, tile):
                num_visible += 1
                tile['in_fog'] = "0"
                break
        if tile['in_fog'] == "1":
            newtile = dict( (key, val) for key, val in tile.items() if key in [
                'xy', 'xystr', 'xyidx', 'x_coordinate', 'y_coordinate', 'x', 'y',
                'terrain_name', 'defense', 'in_fog'])
            tile.clear()
            tile.update(newtile)
    for tile in my_bldgs:
        tile['in_fog'] = "0"
    return num_visible

def new_funds(army_id, tiles_by_idx):
    return len([unit for unit in player_bldgs(army_id, tiles_by_idx) if
                unit['terrain_name'] in CAPTURABLE_TERRAIN]) * 1000


UNIT_DICT_KEYS = [ 'unit_army_id', 'unit_army_name', 'unit_id', 'unit_name',  'moved',
                   'unit_team_name', 'health', 'fuel', 'primary_ammo', 'secondary_ammo' ]

def movedict_xyidx(movedict):
    return int(movedict.get('y_coordinate', movedict.get('yCoordinate', -1)))*1000 + \
        int(movedict.get('x_coordinate', movedict.get('xCoordinate', -1)))

def apply_move(army_id, tiles_by_idx, player_info, move, dbg=False):
    """added to library, so it can be used for forecasting.
    note: in forecasting mode, unfogging doesn't reveal enemy troops.
    returns False if the move is end_turn."""
    def mverr(msg):
        DBGPRINT("ERROR!  "+msg)
    def update_tile_with_dict(tile, update_dict):
        tiles_by_idx[tile['xyidx']].update(update_dict)
    def update_tile_with_unit(tile, unit):
        update_tile_with_dict(tile, dict( (key,val) for key,val in unit.items()
                                          if key in UNIT_DICT_KEYS))
    def del_unit(tile):
        for key in list(tile.keys()):  # copy to avoid chging during iter
            if key in UNIT_DICT_KEYS:
                del tile[key]
    def del_loaded_unit(tile):
        del tile['slot1_deployed_unit_id']
        del tile['slot1_deployed_unit_name']
        del tile['slot1_deployed_unit_health']
    def move_unit(src_tile, dest_tile):
        src_tile['moved'] = '1'
        if src_tile['xyidx'] == dest_tile['xyidx']: return
        update_tile_with_unit(dest_tile, src_tile)
        del_unit(src_tile)
        if can_capture(dest_tile, src_tile, dest_tile['unit_army_id']):
            # undo partial capture
            src_tile['capture_remaining'] = "20"

    #DBGPRINT("move={}".format(move))
    if move.get('stop_worker_num', '') != '':
        return False
    data = move['data']
    if data['end_turn']: return False
    if data['purchase']:
        unit_name = data['purchase']['unit_name']
        castle = tiles_by_idx[movedict_xyidx(data['purchase'])]
        if castle['terrain_name'] != 'Castle':
            return mverr('cannot purchase new unit at {} which is not a castle'.format(
                tilestr(castle)))
        if castle.get('unit_name') not in [None, '']:
            return mverr('cannot purchase new unit at {} which is occupied'.format(
                tilestr(castle)))
        if player_info['funds'] < UNIT_TYPES[unit_name]['cost']:
            return mverr('insufficient funds {} to purchase a {} (cost={}) at {}'.format(
                player_info['funds'], unit_name, UNIT_TYPES[unit_name]['cost'], tilestr(castle)))
        player_info['funds'] -= UNIT_TYPES[unit_name]['cost']
        new_unit_id = 100 + \
            max([int(ifdictnone(tile, 'unit_id', 0)) for tile in tiles_by_idx.values()])
        update_tile_with_dict(castle, {
            'unit_army_id': str(army_id), 'unit_army_name': 'TODO:armyname',
            'unit_id': new_unit_id, 'unit_name': unit_name,
            'unit_team_name': 'foo', 'health': "100", 'fuel': '100',
            'primary_ammo': '100', 'secondary_ammo': '100', 'moved': '1'
        })
        if dbg: DBGPRINT('army_id={} purchase, resulting in {}'.format(
                army_id, tilestr(castle)))
        return True
    # data['move'] == True
    movemove = data['move']
    src_xyidx = dest_xyidx = movedict_xyidx(movemove)
    src_tile = dest_tile = tiles_by_idx[src_xyidx]
    if len(movemove['movements']) > 0:
        dest_xyidx = movedict_xyidx(movemove['movements'][-1])
        dest_tile = tiles_by_idx[dest_xyidx]

    if movemove.get('unit_action', 'simplemove') == 'unloadSlot1':
        if not is_loaded_unicorn(src_tile):
            return mverr("attempted to unload a tile that isn't a loaded Unicorn: {}".format(
                tilestr(src_tile, True)))
        move_unit(src_tile, dest_tile)
        unload_xyidx = int(movemove['y_coord_action'])*1000 + int(movemove['x_coord_action'])
        update_tile_with_dict(tiles_by_idx[unload_xyidx], {
            'unit_army_id': str(army_id), 'unit_army_name': 'TODO:armyname',
            'unit_id': src_tile.get('slot1_deployed_unit_id', 999),
            'unit_name': src_tile['slot1_deployed_unit_name'],
            'health': src_tile['slot1_deployed_unit_health'],
            'unit_team_name': 'TODOunit_team_name', 'fuel': '100',
            'primary_ammo': '100', 'secondary_ammo': '100', 'moved': '1'
        })
        del_loaded_unit(src_tile)
        if dbg: DBGPRINT('army_id={} moved & unloaded unicorn {} onto {}'. format(
                army_id, tilestr(dest_tile), tilestr(tiles_by_idx[unload_xyidx])))
        return True

    if movemove.get('unit_action', 'simplemove') == 'load':
        if len(movemove['movements']) == 0:
            return mverr("can't load without movement: {}".format(tilestr(src_tile, True)))
        if is_loaded_unicorn(dest_tile):
            return mverr("can't load Unicorn that's already loaded: {}".format(
                tilestr(dest_tile, True)))
        if src_tile['unit_name'] not in LOADABLE_UNITS:
            return mverr("can't load this type of unit: {}".format(
                tilestr(src_tile, True)))
        # note: loading does NOT set 'moved' on the unicorn
        update_tile_with_dict(dest_tile, {
            'slot1_deployed_unit_id': dest_tile['unit_id'],
            'slot1_deployed_unit_name': dest_tile['unit_name'],
            'slot1_deployed_unit_health': dest_tile['health'] })
        if dbg: DBGPRINT('army_id={} load unicorn {} from {}'. format(
                army_id, tilestr(dest_tile), tilestr(src_tile)))
        del_unit(src_tile)
        return True

    if movemove.get('unit_action', 'simplemove') == 'join':
        if src_tile['unit_name'] != dest_tile['unit_name']:
            return mverr("attempted to join incompatible types: {} ==> {}".format(
                tilestr(src_tile), tilestr(dest_tile)))
        if is_loaded_unicorn(src_tile):
            return mverr("attempted to join a Unicorn that's already loaded: {}".format(
                tilestr(src_tile, True)))
        if is_loaded_unicorn(dest_tile):
            return mverr("attempted to join to Unicorn that's already loaded: {}".format(
                tilestr(dest_tile, True)))
        dest_tile['health'] = min(unit_health(dest_tile) + unit_health(src_tile), 100)
        del_unit(src_tile)
        return True

    if movemove.get('unit_action', 'simplemove') == 'capture':
        if src_tile.get('unit_name') not in CAPTURING_UNITS:
            return mverr("unit can't capture: {}".format(tilestr(src_tile, True)))
        if dest_tile['terrain_name'] not in CAPTURABLE_TERRAIN:
            return mverr("terrain can't be captured: {}".format(tilestr(dest_tile, True)))
        if is_my_building(dest_tile, army_id):
            return mverr("tile already captured: {}".format(tilestr(dest_tile, True)))
        capture_remaining = get_capture_remaining(dest_tile)
        capture_remaining = max(0, int(capture_remaining) - int(10.0 * unit_health(src_tile) / 100.0))
        move_unit(src_tile, dest_tile)
        dest_tile.update({ 'capture_remaining': str(capture_remaining) })
        if capture_remaining == 0:
            if dbg: DBGPRINT('army_id={} completed capture of {}'.format(army_id, tilestr(dest_tile)))
            dest_tile.update({ 'building_army_id': army_id,
                               'capture_remaining': '20', # reset
                               'building_army_name': "TODOarmy_name",
                               'building_team_name': "TODOteam_name" })
        else:
            if dbg: DBGPRINT('army_id={} capturing {}, capture_remaining={}'.format(
                army_id, tilestr(dest_tile), capture_remaining))
        return True

    if 'x_coord_attack' in movemove:
        if src_tile['unit_name'] not in ATTACKING_UNITS:
            return mverr("unit can't attack: {}".format(tilestr(src_tile, True)))
        defender_xyidx = int(movemove['y_coord_attack'])*1000 + int(movemove['x_coord_attack'])
        defender = tiles_by_idx[defender_xyidx]
        unit_info = UNIT_TYPES[src_tile['unit_name']]
        atkdist = dist(dest_tile, defender)
        if defender.get('unit_name') not in UNIT_TYPES.keys():
            return mverr("can't attack, no unit at dest: {}".format(tilestr(defender, True)))
        if not (unit_info['atkmin'] <= dist(dest_tile, defender) <= unit_info['atkmax']):
            return mverr("attacker {}=>{} not in range [{}-{}] from defender {}".format(
                tilestr(src_tile), tilestr(dest_tile), unit_info['atkmin'], unit_info['atkmax'],
                tilestr(defender)))
        
        move_unit(src_tile, dest_tile)
        attacker = dest_tile
        base_damage = DAMAGE_TBL[attacker['unit_name']][defender['unit_name']]
        attack_weight = unit_health(attacker) / 100.0
        terrain_weight = 1.0 - (TERRAIN_DEFENSE[defender['terrain_name']] / 10.0)
        damage = int(base_damage * attack_weight * terrain_weight)
        if dbg: DBGPRINT('army_id={} attack {} vs {} dhealth={} dmg={}'.format(
                army_id, tilestr(attacker), tilestr(defender), defender['health'], damage))
        move['__attack'] = {'attacker':tilestr(attacker), 'attacker_health': attacker['health'],
                            'defender': tilestr(defender), 'defender_health': defender['health'],
                            'damage': damage }
        defender['health'] = str(unit_health(defender) - damage)
        rdamage = 0
        if unit_health(defender) <= 0:
            del_unit(defender)
            move['__attack']['return_damage'] = ATTACK_DEFENDER_KILLED
            if dbg: DBGPRINT('=> defender killed')
        elif defender['unit_name'] in RETURNS_FIRE_UNITS:
            rbase_damage = DAMAGE_TBL[defender['unit_name']][attacker['unit_name']]
            rattack_weight = unit_health(defender) / 100.0
            rterrain_weight = 1.0 - (TERRAIN_DEFENSE[attacker['terrain_name']] / 10.0)
            rdamage = int(rbase_damage * rattack_weight * rterrain_weight)
            move['__attack']['return_damage'] = rdamage
            if dbg: DBGPRINT('=> return dmg={} vs attacker health={}'.format(
                    rdamage, attacker['health']))
            attacker['health'] = str(unit_health(defender) - rdamage)
            if unit_health(attacker) <= 0:
                move['__killed_atk'] = copy.deepcopy(attacker)
                del_unit(attacker)
                move['__attack']['return_damage'] = ATTACK_ATTACKER_KILLED
                if dbg: DBGPRINT('=> attacker killed')
        return True

    # simple movement
    if len(movemove['movements']) > 0:
        if dbg: DBGPRINT('army_id={} moved {} ==> {}'. format(
                army_id, tilestr(src_tile), tilestr(dest_tile)))
        move_unit(src_tile, dest_tile)
    else:
        src_tile['moved'] = '1'
    return True

def attack_strength(unit):
    return ATTACK_STRENGTH[unit['unit_name']] * unit_health(unit) / 100.0

def defense_strength(unit):
    return DEFENSE_STRENGTH[unit['unit_name']] * unit_health(unit) / 100.0 * \
        (1.0 - (TERRAIN_DEFENSE[unit['terrain_name']] / 10.0))

def score_position(army_id, tiles_by_idx, move=None):
    # TODO: capture in progress and units that can't finish capture bec of attacks
    # TODO: Enemy has less visibility -- also accounts for pushing back
    # TODO: Special bonus for trying to capture castles and enemy hq
    parse_tiles_by_idx(army_id, tiles_by_idx)
    num_visible = set_fog_values(army_id, tiles_by_idx)
    # More board visible (less fog) -- also accounts for moving to 'front line'
    pct_visible = int((100.0 * num_visible) / len(tiles_by_idx))
    production_capacity = len(MY_CASTLES) + len(MY_TOWNS)
    num_my_units = len(MY_UNITS)
    # scale to assuming 10 units before overwhelming other factors
    sum_attack_strength = int(sum([attack_strength(unit)*unit_health(unit)/1000.0
                                   for unit in MY_UNITS]))
    sum_defense_strength = int(sum([defense_strength(unit)*unit_health(unit)/1000.0
                                    for unit in MY_UNITS]))
    # square the score to skew move choice to better moves...
    score = num_my_units * 10 + production_capacity * 10 + pct_visible + \
            sum_attack_strength + sum_defense_strength
    msg = "{} = #units*10({}) + prod*10({}) + %vis({:02d}) + atk({}) + def({}): {}".format(
        score, num_my_units * 10, production_capacity * 10, pct_visible,
        sum_attack_strength, sum_defense_strength, movestr(move) if move else "") if \
        DBG_SCORING else ""
    return score, msg

    
def score_move(army_id, tiles_by_idx, player_info, move):
    if move.get('stop_worker_num', '') != '':
        return 0, 0, ""
    tiles_by_idx = copy.deepcopy(tiles_by_idx)
    player_info = copy.deepcopy(player_info)

    # TODO: detect HQ capture - this is just to avoid divide-by-zero errors
    capturable_tiles = [tile for tile in tiles_by_idx.values()
                        if tile['terrain_name'] in CAPTURABLE_TERRAIN
                        and tile.get('building_army_id') != army_id]
    attackable_units = [tile for tile in tiles_by_idx.values() if
                        tile.get('unit_army_id') not in [None, army_id]]
    if len(capturable_tiles) == 0:
        print("WINNER!  nothing left to capture.  army_id={}".format(army_id))
        sys.exit(0)
    
    # very basic algorithm -- subtly, these rules increase game speed by reducing the search space
    # - preferring moves which attack nearby enemies
    # - preferring moves which bring enemies closer together
    # obviously, this is (highly) suboptimal, but it plays games 10x faster to help accelerate
    # learning...
    multiplier = 1.0
    if move['data']['move']:  # ignore false
        movemove = move['data']['move']
        dest_xyidx = movedict_xyidx(movemove)
        dest_tile = tiles_by_idx[dest_xyidx]
        unit_max_move = float(max_travel(dest_tile))
        if 'x_coord_attack' in movemove:
            multiplier *= 4.0
            # TODO: bonus for healing injured units
            # TODO: bonus for killing enemy
            # TODO: scale bonus for more damage bec it means they can do less damage to us
            #  (ideally, scale *that* to damage this partic enemy unit can do to our known
            #  nearby units)
        elif movemove.get('unit_action', '') == 'capture':
            multiplier *= 2.5
            # TODO: bonus for completing capture
            # TODO: bonus for stealing from enemy
            # bonus for attacking enemy
        if len(movemove['movements']) > 0:
            dest_xyidx = movedict_xyidx(movemove['movements'][-1])
            dest_tile = tiles_by_idx[dest_xyidx]
        turns_to_tgt_tile = {}
        # can't be empty - see above re capturable_tiles
        for tgt_tile in capturable_tiles + attackable_units:
            turns_to_tgt_tile[tgt_tile['xyidx']] = max(
                1.0, dist(dest_tile, tgt_tile) / unit_max_move)
        # avg top 3 nearest dests to provide variety vs competition from our other units
        avg_dist = max(0.5, numpy.average(sorted(turns_to_tgt_tile.values())[0:3]))
        if DBG_SCORING_DETAIL:
            top3dist = sorted(turns_to_tgt_tile.items(), key=lambda r: r[1])[0:3]
            DBGPRINT('{} avgdist={:.2f}: {}'.format(
                tilestr(dest_tile), avg_dist,
                ", ".join(['{}@{}'.format(val, xyidxstr(key)) for key,val in top3dist])))
        multiplier *= (1.0 + (0.8/avg_dist))

    res = apply_move(army_id, tiles_by_idx, player_info, move)
    if res is None:
        DBGPRINT("bad move {}: skipping...".format(move))
        return 0, 0, ""
    pos_score, msg = score_position(army_id, tiles_by_idx, move)
    # note that purchase gets the lowest score, with a base of 0.0 i.e. it comes last
    score = multiplier * pos_score
    if DBG_SCORING:
        msg = "score: {:.2f} = mult({:.2f}) * base={}".format(score, multiplier, msg)
    return score, pos_score, msg

def initialize_player_turn(army_id, tiles_by_idx, player_info, game_state):
    game_state['botPlayerId'] = int(player_info['player_id'])
    player_info['funds'] = int(player_info.get('funds', 0)) + new_funds(army_id, tiles_by_idx)
    for tile in tiles_by_idx.values():
        tile['moved'] = '0'

