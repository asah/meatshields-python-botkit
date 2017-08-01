#!/usr/bin/env python
#
# pylint:disable=locally-disabled,fixme,bad-whitespace,missing-docstring,multiple-imports,global-statement,multiple-statements,no-self-use,too-few-public-methods,
#
# basicbot.py
#
# TODO list:
# - walk over friends, but not land on them
# - Unicorn loading & unloading
# - Unicorn moves 6 when loaded
# - healing
# - multiple enemies
#
# note: algorithm improvements are deferred for machine learning, for now just use random
#
import random, re, os, copy, datetime
from flask import Flask, request, json, make_response
from flask_restful import Resource, Api

DEBUG = (os.environ.get('FLASK_DEBUG', '0') == '1')

# use env vars to turn on verbose debugging -- more control and shuts up pylint
DBG_MOVEMENT = (os.environ.get('DBG_MOVEMENT', '1') == '1')
DBG_PARSE_TIME = (os.environ.get('DBG_PARSE_TIME', '0') == '1')
DBG_PRINT_SHORTCODES = (os.environ.get('DBG_PRINT_SHORTCODES', '0') == '1')

APP = Flask(__name__)
API = Api(APP)

# remember turns and moves between API calls - helps debugging
GAMES = {}
LAST_MOVES = {}

@APP.before_request
def set_random_seed():
    random.seed(1337)   # reproducibility

class Heartbeat(Resource):
    def post(self):
        return { "status": "success", "data": "OK" }

def mkres(**args):
    """ e.g. mkres(move={"x_coordinates": ... }) """
    res = { "purchase": False, "end_turn": False, "move": False }
    res.update(args)
    return { "status": "success", "data": res }

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
    'Knight':       { 'cost':  1000, 'move': 3, 'attackmin': 1, 'attackmax': 1 },
    'Unicorn':      { 'cost':  1000, 'move': 4, 'attackmin': 0, 'attackmax': 0 },
    'Archer':       { 'cost':  2000, 'move': 2, 'attackmin': 2, 'attackmax': 3 },
    'Ninja':        { 'cost':  3000, 'move': 2, 'attackmin': 1, 'attackmax': 1 },
    # mounts are doubled for easier integer math
    'Mount':        { 'cost':  4000, 'move': 8, 'attackmin': 1, 'attackmax': 1 },
    'Boulder':      { 'cost':  6000, 'move': 5, 'attackmin': 2, 'attackmax': 3 },
    'Mage':         { 'cost':  6000, 'move': 6, 'attackmin': 1, 'attackmax': 1 },
    'Centaur':      { 'cost':  7000, 'move': 6, 'attackmin': 1, 'attackmax': 1 },
    'Brimstone':    { 'cost': 15000, 'move': 4, 'attackmin': 3, 'attackmax': 4 },
    'Troll':        { 'cost': 16000, 'move': 6, 'attackmin': 1, 'attackmax': 1 },
    'Giant':        { 'cost': 22000, 'move': 6, 'attackmin': 1, 'attackmax': 1 },
    'Thunderstorm': { 'cost': 28000, 'move': 4, 'attackmin': 3, 'attackmax': 5 },
}

UNIT_SHORTCODES = dict([(tkey, tkey[0]) for tkey in UNIT_TYPES.keys()])
UNIT_SHORTCODES.update({ 'Brimstone': 'R', 'Thunderstorm': 'H', 'Mage': 'E' })
UPPER_SHORTCODES_UNIT = dict([(tval,tkey) for tkey,tval in UNIT_SHORTCODES.items()])
LOWER_SHORTCODES_UNIT = dict([(tval.lower(),tkey) for tkey,tval in UNIT_SHORTCODES.items()])

CAPTURING_UNITS = set('Knight Archer Ninja'.split())
ATTACKING_UNITS = set([ukey for ukey,uval in UNIT_TYPES.items() if uval['attackmin'] > 0])
MISSILE_UNITS =   set([ukey for ukey,uval in UNIT_TYPES.items() if uval['attackmin'] > 1])

MY_HQ, OTHER_HQ = None, []
MY_UNITS, ENEMY_UNITS = [], []
MY_CASTLES, OTHER_CASTLES = [], []
MY_TOWNS, OTHER_TOWNS = [], []
TILES_BY_IDX = {}

TILE_DEFAULT_VALUES = dict([(tdv_fld,None) for tdv_fld in re.split(r'[ ,\r\n]+', """
  building_army_id,building_army_name,building_team_name,capture_remaining,
  deployed_unit_id,fuel,health,moved,primary_ammo,secondary_ammo,
  slot1_deployed_unit_health,slot1_deployed_unit_id,slot1_deployed_unit_name,
  slot2_deployed_unit_id,unit_army_id,unit_army_name,
  unit_id,unit_name,unit_team_name""")])

TILE_KNOWN_FIELDS = list(TILE_DEFAULT_VALUES.keys()) + [
    'terrain_name', 'x_coordinate', 'y_coordinate', 'xy', 'xyidx', 'xystr'
]

def is_first_move_in_turn(game_id):
    last_move = LAST_MOVES.get(game_id)
    if last_move is None: return True # very first move!
    # if last_move is end_turn, then it's the 1st move of the next turn
    return last_move['data']['end_turn']

def tile2xystr(tile):
    """indexed from 0"""
    return "{:02d},{:02d}".format(tile['x'], tile['y'])

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
    compact_response = re.sub(r'(?m)\r?\n +"(yCoord|y_coord)', r' "\1', compact_response)
    # keep __unit_name on the same line as  __unit_action
    # keep building_army_name and building_team_name on the same line as building_army_id
    # keep 
    compact_response = re.sub(
        r'(?m)\r?\n +"(__unit_name|building_army_name|building_team_name|'+
        r'health|secondary_ammo|unit_army_name|unit_id|unit_name|unit_team_name)',
        r' "\1', compact_response)
    return compact_response

def pathstr(path, show_terrain=False):
    if path is None: return "{}"
    if len(path) == 0: return "[]"
    return ("; " if show_terrain else ";").join([
        (("{}@{}".format(tile['terrain_name'][0:4], tile2xystr(tile)))
         if show_terrain else tile2xystr(tile)) for tile in path])

def tilestr(tile, show_details=False):
    """canonical way to display a tile's location, terrain and (if present) unit.
    units are shortened to 3 chars, terrain to 4, which helps standardize formatting.
    army #1 units are printed is like this: unic  (for unicorn)
    army #2 units are printed is like this: Unic
    army #3 units are printed is like this: UNic
    army #4 units are printed is like this: UNIc
    army #5 units are printed is like this: UNIC.
    show_details=True is meant for one-line-per-tile output"""
    # TODO: show_details
    if tile['unit_name'] in [None, ""]:
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
    return "{}@{:02d},{:02d}:{}{}".format(
        tile['terrain_name'][0:4], tile['x'], tile['y'], unit_name, details)

def has_unit(tile):
    return (tile.get('unit_name', '') not in [None, ''])

def is_my_building(tile, army_id):
    return tile.get('building_army_id', '') == army_id

def can_capture(tile, unit, army_id):
    return (tile['terrain_name'] in CAPTURABLE_TERRAIN and unit['unit_name'] in CAPTURING_UNITS and
            not is_my_building(tile, army_id))

def xyneighbors(tile, exclude_tiles, unit_present=None):
    """exclude_tiles is a list of tiles to exclude;
    unit_present=True: exclude empty tiles; unit_present=False: exclude filled tiles"""
    excl_xyidxs = set([excl['xyidx'] for excl in exclude_tiles])
    return [neighbor for neighbor in
            [TILES_BY_IDX.get(tile['xyidx']+1, None), TILES_BY_IDX.get(tile['xyidx']-1, None),
             TILES_BY_IDX.get(tile['xyidx']+1000, None), TILES_BY_IDX.get(tile['xyidx']-1000, None)]
            if neighbor is not None and neighbor['xyidx'] not in excl_xyidxs and
            ((unit_present is None) or
             (unit_present is True and has_unit(neighbor)) or
             (unit_present is False and not has_unit(neighbor))) ]

def unit_neighbors(tile, army_id, unit_tile, remaining_moves, prev, path):
    # counted down to the end
    if DBG_MOVEMENT:
        APP.logger.debug(
            'unit_neighbors(tile={}, unit_tile={}, remaining_moves={}, prev={}, path={}'.format(
                tilestr(tile), tilestr(unit_tile), remaining_moves, tilestr(prev), pathstr(path)))
    unit_type = unit_tile['unit_type']
    # enemy tile - no neighbors allowed
    if tile['unit_army_id'] not in [None, army_id]: return []
    terrain = tile['terrain_name']
    # impassable by any unit types
    if terrain not in WALKABLE_TERRAIN: return []
    # impassable by this unit type
    decr_moves = 0
    if unit_type == 'Knight':
        if terrain in NORMAL_TERRAIN: decr_moves = 1
        elif terrain in WALKABLE_TERRAIN: decr_moves = 2
    elif unit_type in ['Archer','Ninja']:
        if terrain in WALKABLE_TERRAIN: decr_moves = 1
    elif unit_type in ['Mount', 'Brimstone', 'Thunderstorm']:
        if terrain in ['Plains','Forest']: decr_moves = 2
        elif terrain in NORMAL_TERRAIN: decr_moves = 1
    elif unit_type == 'Mount':
        if terrain in ['Plains','Forest']: decr_moves = 2
        elif terrain in NORMAL_TERRAIN: decr_moves = 1
    else:
        if terrain == 'Forest': decr_moves = 2
        elif terrain in NORMAL_TERRAIN: decr_moves = 1
    if DBG_MOVEMENT:
        APP.logger.debug('decr_moves={} vs  remaining={}'.format(decr_moves, remaining_moves))
    if decr_moves == 0: return []  # impassable by this unit type
    if remaining_moves < decr_moves: return [] # too far
    immediate_neighbors = [neighbor for neighbor in xyneighbors(tile, [prev, unit_tile])
                           if neighbor['seen'] == 0 and neighbor['unit_army_id'] is None]
    if DBG_MOVEMENT:
        APP.logger.debug('neighbors of {}: {}, path:{}, moves left:{}'.format(
            tilestr(tile), pathstr(immediate_neighbors), pathstr(path),
            remaining_moves - decr_moves))
    res = [] if tile['xyidx'] == unit_tile['xyidx'] else [tile]
    for immediate_neighbor in immediate_neighbors:
        newpath = path + ([tile] if tile['xyidx'] != unit_tile['xyidx'] else [])
        newres = unit_neighbors(immediate_neighbor, army_id, unit_tile,
                                remaining_moves - decr_moves, tile, newpath)
        for rec in newres:
            rec['seen'] = 1
            if rec['path'] is None:
                rec['path'] = newpath
            res.append(rec)
    return res

def dist(unit, tile):
    """euclidean distance - used for missile attacks and a (bad) approximation of travel time."""
    return abs(tile['x'] - unit['x']) + abs(tile['y'] - unit['y'])

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
    APP.logger.debug(res)
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
        #APP.logger.debug(tile)
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

def tile2xyidx(tile):
    return tile['y']*1000 + tile['x']

def idx2xy(xyidx):
    return int(xyidx / 1000), xyidx % 1000

def set_xy_fields(tile):
    # support compact representation
    if 'xy' in tile:
        tile['x_coordinate'], tile['y_coordinate'] = tile['xy'].split(',')
    else:
        tile['xy'] = tile['x_coordinate'] + ',' + tile['y_coordinate']
    tile['x'], tile['y'] = int(tile['x_coordinate']), int(tile['y_coordinate'])
    tile['xystr'], tile['xyidx'] = tile2xystr(tile), tile2xyidx(tile)
    return tile

def parse_map(army_id, tiles, game_info):
    global MY_HQ, OTHER_HQ, MY_UNITS, ENEMY_UNITS, MY_CASTLES
    global OTHER_CASTLES, MY_TOWNS, OTHER_TOWNS, TILES_BY_IDX
    MY_HQ, OTHER_HQ = None, []
    MY_UNITS, ENEMY_UNITS = [], []
    MY_CASTLES, OTHER_CASTLES = [], []
    MY_TOWNS, OTHER_TOWNS = [], []
    TILES_BY_IDX = {}
    notable_tiles = []
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
                #APP.logger.debug('{}: {}'.format(tile['xy'], tile))
    # old style, including army details
    for tile_ar in tiles:
        for tile in tile_ar:
            tile = set_xy_fields(tile)
            if '__tilemap' in game_info:
                if tile['xyidx'] not in TILES_BY_IDX:
                    raise Exception("bad tile index {} - tilemap doesn't match JSON?".format(
                        tile['xyidx']))
                TILES_BY_IDX[tile['xyidx']].update(tile)
            else:
                TILES_BY_IDX[tile['xyidx']] = tile
    tiles = list(TILES_BY_IDX.values())
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
    notable_tiles = sorted(notable_tiles, key=lambda tile: tile['xystr'])
    APP.logger.debug("notable_tiles:  my army_id={}\n{}".format(
        army_id, "\n".join([tilestr(tile, show_details=True) for tile in notable_tiles])))

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

def my_units_by_dist():
    # todo: support multiple enemies
    units_by_dist = sorted(MY_UNITS, key=lambda tile: dist(OTHER_HQ[0], tile))
    dbg_units = ["units by distance:"]
    for unit in units_by_dist:
        dbg_units.append("{}{}: {:.0f} from enemy hq [{},{}]: {}".format(
            "moved " if str(unit['moved'])=='1' else "", tilestr(unit),
            dist_from_enemy_hq(unit), OTHER_HQ[0]['x'], OTHER_HQ[0]['y'],
            tile_details_str(unit, ['moved'])))
    APP.logger.debug("\n".join(dbg_units))
    return units_by_dist

def msec(timedelta):
    return timedelta.seconds*1000 + int(timedelta.microseconds/1000)

def choose_move(player_id, army_id, game_info, players):
    my_info = players[player_id]
    # debug hack to force the algorithm to 'pick' this tile for the move,
    # building units at a castle, moving a unit, etc.
    dbg_force_tile = game_info.get('dbg_force_tile', '')   # x,y padded with zeroes, e.g. 04,14
    #todo: dbg_force_action = game_info.get('dbg_force_action', '')

    # for each unit ordered by nearest to the enemy HQ
    # - if castle can be captured, capture it
    # - if village can be captured, capture it
    # - if enemy can be attacked, attack it
    # - else move randomly
    # for each castle, order by nearest to the enemy flag:
    # - create the strongest unit we can given remaining funds

    # TODO: what to move?  for now, lemmings to the slaughter
    dbg_nbrs = []
    if dbg_force_tile != '':
        APP.logger.debug("dbg_force_tile: {}".format(dbg_force_tile))
    for unit in my_units_by_dist():
        if str(unit['moved'])=='1': continue
        if dbg_force_tile not in ['', unit['xystr']]: continue
        unit_type = unit['unit_name']

        # don't move, just capture.
        # note dumb alg, e.g. unit with tiny health will still try...
        if unit['capture_remaining'] not in [None, ""] and \
           int(unit['capture_remaining']) > 0 and \
           can_capture(unit, unit, army_id) and \
           random.random() < 0.90:
            move = { 'x_coordinate': unit['x_coordinate'], 'y_coordinate': unit['y_coordinate'],
                     '__unit_name': unit_type, '__unit_action': 'capture',
                     'movements': [], 'unit_action': 'capture' }
            return mkres(move=move)

        # randomly choose a direction to walk
        # TODO: Unicorn moves 6 when loaded
        unit['seen'] = 1
        unit['path'] = []
        for tile in TILES_BY_IDX.values():
            tile['seen'] = 0
            tile['path'] = None
        unit_max_move = unit['unit_type']['move']
        # not moving is a valid choice
        move = { 'x_coordinate': unit['x_coordinate'], 'y_coordinate': unit['y_coordinate'] }
        neighbors = unit_neighbors(unit, army_id, unit, unit_max_move, unit, [])
        neighbors.append(unit)
        dest = random.choice(neighbors)
        if dest['xy'] == unit['xy']:
            dbg_nbrs.append("no walkable neighbors for {}, move={}:".format(
                tilestr(unit), unit_max_move))
            move.update(
                { '__unit_name': unit_type, '__unit_action': 'no_movement', 'movements': [] })
        else:
            dest['path'].append(dest)
            move.update(
                { '__unit_name': unit_type, '__unit_action': 'simple_movement',
                  'movements': [ { "xCoordinate": p['x'], "yCoordinate": p['y'],
                                   '__terrain': p['terrain_name'] }
                                 for p in dest['path']] })
            dbg_nbrs.append("walkable neighbors of {}, move={}:".format(
                tilestr(unit), unit_max_move))
            for nbr in sorted(neighbors, key=lambda r: r['xystr']):
                dbg_nbrs.append("{} {} via {}".format(
                    "=>" if dest['xy']==nbr['xy'] else " -",
                    tilestr(nbr), pathstr(nbr['path'], show_terrain=True)))
        APP.logger.debug("\n".join(dbg_nbrs))

        # usually capture open towns, castles and headquarters
        if can_capture(dest, unit, army_id) and random.random() < 0.90:
            move["unit_action"] = "capture"            
            move['__action'] = 'capture' # harmless - for easier development
        elif unit_type in ATTACKING_UNITS:
            # missile units: don't move, just attack
            attack_tile = unit if unit_type in MISSILE_UNITS else dest
            attackmin, attackmax = unit['unit_type']['attackmin'], unit['unit_type']['attackmax']
            attack_neighbors = [enemy_unit for enemy_unit in ENEMY_UNITS
                                if attackmin <= dist(attack_tile, enemy_unit) <= attackmax]
            dbgmsgs = [ "enemy units from {}".format(tilestr(attack_tile)) ]
            dbgmsgs.append("\n".join(["{}: {}".format(
                dist(attack_tile, enemy_unit), tilestr(enemy_unit)) for enemy_unit in ENEMY_UNITS]))
            dbgmsgs.append("attack_neighbors for {}: {}".format(
                tilestr(dest), "\n".join([pathstr(tile['path']) for tile in attack_neighbors])))
            random.shuffle(attack_neighbors)
            for attack_neighbor in attack_neighbors:
                dbgmsgs.append("- {}".format(tilestr(attack_neighbor, show_details=True)))
                if attack_neighbor.get('unit_army_id', '') not in ['', None, army_id] and \
                   random.random() <= 0.9:
                    dbgmsgs.append("attacking: {}".format(tilestr(attack_neighbor)))
                    move['x_coord_attack'] = attack_neighbor['x']
                    move['y_coord_attack'] = attack_neighbor['y']
                    # missile units: don't move, just attack
                    if unit_type in MISSILE_UNITS:
                        move['movements'] = []
                        move['__action'] = 'missile_attack'
                    else:
                        move['__action'] = 'ground_attack'
                    break
            APP.logger.debug("\n".join(dbgmsgs))
        return mkres(move=move)
    return build_new_units(my_info, dbg_force_tile)

def build_new_units(my_info, dbg_force_tile):
    # build new units at castles
    my_castles_by_dist = sorted(MY_CASTLES, key=dist_from_enemy_hq)
    dbg_castles = ["castles by distance:"]
    for castle in my_castles_by_dist:
        dbg_castles.append("{}: {:.1f} from enemy hq @{}".format(
            tilestr(castle, show_details=True), dist_from_enemy_hq(castle),
            tile2xystr(OTHER_HQ[0])))
    APP.logger.debug("\n".join(dbg_castles))
    funds = int(my_info['funds'])
    for castle in my_castles_by_dist:
        if dbg_force_tile not in ['', castle['xystr']]: continue
        if castle['unit_army_id'] is None and funds >= 1000:
            unit_types = [k for k,v in UNIT_TYPES.items() if v['cost'] <= funds]
            # randomly choose the unit type
            newunit = random.choice(unit_types)
            return mkres(purchase = {
                'x_coordinate': castle['x_coordinate'], 'y_coordinate': castle['y_coordinate'],
                'unit_name': newunit})
    return mkres(end_turn=True)

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

class BasicNextMove(Resource):
    def post(self):
        if DBG_PRINT_SHORTCODES:
            APP.logger.debug("\n".join(["{}: {}".format(name, typ) for name, typ in
                                        sorted(TERRAIN_SHORTCODES.items())]))
            APP.logger.debug("\n".join(["{}: {}".format(name, typ) for name, typ in
                                        sorted(UNIT_SHORTCODES.items())]))
        start_time = datetime.datetime.now()
        if request.data:
            jsondata = json.loads(request.data)
            player_id = str(jsondata['botPlayerId'])
            game_info = jsondata['gameInfo']
        else:
            player_id = str(request.form['botPlayerId'])
            game_info = json.loads(request.form['gameInfo'])
        parse_time = datetime.datetime.now() - start_time
        if DBG_PARSE_TIME:
            APP.logger.debug('JSON parse time: {}'.format(msec(parse_time)))

        if DEBUG:
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
        army_id = players.get(player_id, {}).get('army_id', '')
        parse_map(army_id, tiles, game_info)
        tiles_list = TILES_BY_IDX.values()
        if is_first_move_in_turn(game_info['game_id']):
            APP.logger.debug("tilemap:\n" + tilemap_json(tiles_list))
            APP.logger.debug("unitmap:\n" + unitmap_json(tiles_list, army_id))
        move = choose_move(player_id, army_id, game_info, players)
        if move['data']['end_turn']:
            APP.logger.debug("tilemap:\n" + tilemap_json(tiles_list))
            APP.logger.debug("unitmap:\n" + unitmap_json(tiles_list, army_id))

        # save the game, for debugging
        if DEBUG:
            game_info_json = compact_json_dumps(compressed_game_info(game_info, army_id))
            game_fh = open('game-{}.json'.format(game_id), 'w')
            game_fh.write('{} "botPlayerId": {}, "gameInfo": {} {}'.format(
                "{", player_id, game_info_json, "}"))
            game_fh.close()

        LAST_MOVES[game_id] = move
            
        # compact response helps debugging
        if DEBUG:
            APP.logger.debug("move response: \n{}".format(compact_json_dumps(move)))
            response = make_response(compact_json_dumps(move))
            response.headers['content-type'] = 'application/json'
            return response
        return move

API.add_resource(Heartbeat, '/meatshields/bot/getHeartbeat')
API.add_resource(BasicNextMove, '/meatshields/bot/getNextMove')

if __name__ == '__main__':
    APP.run(debug=DEBUG)
