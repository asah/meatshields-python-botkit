#!/usr/bin/env python
#

# pylint:disable=locally-disabled,fixme,bad-whitespace,missing-docstring,multiple-imports,global-statement,multiple-statements,no-self-use,too-few-public-methods,
#
# basicbot.py
#
# TODO list:
# - Unicorn loading & unloading
# - Unicorn moves 6 when loaded
# - healing
#
# note: all algorithm improvements are deferred for machine learning, for now just use random
#
import random, re, os
from flask import Flask, request, json, make_response
from flask_restful import Resource, Api

DEBUG = (os.environ.get('FLASK_DEBUG', '0') == '1')

APP = Flask(__name__)
API = Api(APP)

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
WALKABLE_TERRAIN_TYPES = set(list(NORMAL_TERRAIN) + ['Forest','Mountains','River'])
CAPTURABLE_TERRAIN = set(['Headquarters','Castle','Town'])

UNIT_TYPES = {
    'Knight':       { 'cost':  1000, 'move': 3, 'attackmin': 1, 'attackmax': 1 },
    'Unicorn':      { 'cost':  1000, 'move': 4, 'attackmin': 0, 'attackmax': 0 },
    'Archer':       { 'cost':  2000, 'move': 2, 'attackmin': 2, 'attackmax': 3 },
    'Ninja':        { 'cost':  3000, 'move': 2, 'attackmin': 1, 'attackmax': 1 },
    'Mount':        { 'cost':  4000, 'move': 8, 'attackmin': 1, 'attackmax': 1 },
    'Boulder':      { 'cost':  6000, 'move': 5, 'attackmin': 2, 'attackmax': 3 },
    'Mage':         { 'cost':  6000, 'move': 6, 'attackmin': 1, 'attackmax': 1 },
    'Centaur':      { 'cost':  7000, 'move': 6, 'attackmin': 1, 'attackmax': 1 },
    'Brimstone':    { 'cost': 15000, 'move': 4, 'attackmin': 3, 'attackmax': 4 },
    'Troll':        { 'cost': 16000, 'move': 6, 'attackmin': 1, 'attackmax': 1 },
    'Giant':        { 'cost': 22000, 'move': 6, 'attackmin': 1, 'attackmax': 1 },
    'Thunderstorm': { 'cost': 28000, 'move': 4, 'attackmin': 3, 'attackmax': 5 },
}
CAPTURING_UNITS = set('Knight,Archer,Ninja'.split(','))
ATTACKING_UNITS = set([key for key,val in UNIT_TYPES.items() if val['attackmin'] > 0])
MISSILE_UNITS =   set([key for key,val in UNIT_TYPES.items() if val['attackmin'] > 1])

MY_HQ, OTHER_HQ = None, []
MY_UNITS, THEIR_UNITS = [], []
MY_CASTLES, OTHER_CASTLES = [], []
MY_TOWNS, OTHER_TOWNS = [], []
TILES_BY_IDX = {}

def xystr(tile):
    return "{:02d},{:02d}".format(tile['x'],tile['y'])

def xyloc(tile):
    return tile['y']*1000 + tile['x']

def compact_json_dumps(data):
    compact_response = json.dumps(data, indent=2, sort_keys=True)
    compact_response = re.sub(r'(?m){\r?\n +', '{ ', compact_response)
    compact_response = re.sub(r'(?m)\r?\n +}', ' }', compact_response)
    if re.search(r'x_coord_attack', compact_response):
        # key sorting doesn't work nicely with x/y_coord_attack
        compact_response = re.sub(
            r'(?m)("x_coordinate": "[0-9]+")([, \r\n]+)("y_coord_attack": [0-9]+)',
            r'\3\2\1', compact_response)
    compact_response = re.sub(r'(?m)\r?\n +"(yCoord|y_coord)', r' "\1', compact_response)
    return compact_response

def pathstr(path, show_terrain=False):
    if path is None: return "{}"
    if len(path) == 0: return "[]"
    return ("; " if show_terrain else ";").join([
        (("{}@{}".format(tile['terrain_name'][0:4], xystr(tile)))
         if show_terrain else xystr(tile)) for tile in path])

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
        details_dict = dict_strip_none(tile)
        details = repr(dict([(k,v) for k,v in details_dict.items()
                             if k not in 'terrain_name,x,y,unit_name,xyloc,xystr'.split()]))
    return "{}@{:02d},{:02d}:{} {}".format(
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
    excl_xylocs = [excl['xyloc'] for excl in exclude_tiles]
    return [neighbor for neighbor in
            [TILES_BY_IDX.get(xyloc(tile)+1, None), TILES_BY_IDX.get(xyloc(tile)-1, None),
             TILES_BY_IDX.get(xyloc(tile)+1000, None), TILES_BY_IDX.get(xyloc(tile)-1000, None)]
            if neighbor is not None and neighbor['xyloc'] not in excl_xylocs and
            ((unit_present is None) or
             (unit_present is True and has_unit(neighbor)) or
             (unit_present is False and not has_unit(neighbor))) ]

def unit_neighbors(tile, army_id, unit_tile, remaining_moves, prev, path):
    # counted down to the end
    # TODO: test fractional case e.g. Boulder walking through Forest
    APP.logger.debug('unit_neighbors(tile={}, unit_tile={}, prev={}, path={}'.format(
        tilestr(tile), tilestr(unit_tile), tilestr(prev, show_details=True), pathstr(path)))
    unit_type = unit_tile['unit_type']
    # enemy tile - no neighbors allowed
    if tile['unit_army_id'] not in [None, army_id]: return []
    terrain = tile['terrain_name']
    # impassable by any unit types
    if terrain not in WALKABLE_TERRAIN_TYPES: return []
    # impassable by this unit type
    decr_moves = 0
    if unit_type == 'Knight':
        if terrain in NORMAL_TERRAIN: decr_moves = 1
        elif terrain in ['Forest','River','Mountains']: decr_moves = 2
    elif unit_type in ['Archer','Ninja']:
        decr_moves = 1
    elif unit_type == 'Mount':
        if terrain in ['Road','Bridge']: decr_moves = 1
        elif terrain in NORMAL_TERRAIN: decr_moves = 2
    else: # normal walking units
        if terrain in NORMAL_TERRAIN: decr_moves = 1
        elif terrain == 'Forest': decr_moves = 2
    APP.logger.debug('decr_moves={} vs  remaining_moves={}'.format(
        decr_moves, remaining_moves))
    if decr_moves == 0: return []  # impassable by this unit type
    if remaining_moves < 1: return [tile]
    immediate_neighbors = [neighbor for neighbor in xyneighbors(tile, [prev, unit_tile])
                           if neighbor['seen'] == 0 and neighbor['unit_army_id'] is None]
    APP.logger.debug('neighbors of {}: {}, path:{}, moves left:{}'.format(
        tilestr(tile), pathstr(immediate_neighbors), pathstr(path), remaining_moves - decr_moves))
    res = [] if tile['xyloc'] == unit_tile['xyloc'] else [tile]
    for immediate_neighbor in immediate_neighbors:
        newpath = path + ([tile] if tile['xyloc'] != unit_tile['xyloc'] else [])
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
    return abs(tile['x'] - tile['y']) + abs(unit['x'] - unit['y'])

def dict_strip_none(mydict):
    return dict([(k,v) for k,v in mydict.items() if v is not None and k not in [
        'primary_ammo','secondary_ammo','building_team_name','unit_army_name','defense',
        'building_army_name','deployed_unit_id','slot1_deployed_unit_id','slot2_deployed_unit_id',
        'tile_id','unit_id','unit_team_name' ]])

def parse_map(army_id, tiles):
    global MY_HQ, OTHER_HQ, MY_UNITS, THEIR_UNITS, MY_CASTLES
    global OTHER_CASTLES, MY_TOWNS, OTHER_TOWNS, TILES_BY_IDX
    MY_HQ, OTHER_HQ = None, []
    MY_UNITS, THEIR_UNITS = [], []
    MY_CASTLES, OTHER_CASTLES = [], []
    MY_TOWNS, OTHER_TOWNS = [], []
    TILES_BY_IDX = {}
    notable_tiles = []
    for tile_ar in tiles:
        for tile in tile_ar:
            tile['x'], tile['y'] = int(tile['x_coordinate']), int(tile['y_coordinate'])
            tile['xyloc'], tile['xystr'] = xyloc(tile), xystr(tile)
            TILES_BY_IDX[tile['xyloc']] = tile
            # fk it, just copy all the fields i.e. copy the whole tile
            #APP.logger.debug("{}".format(dict_strip_none(tile)))
            if tile['unit_army_id'] not in ["", None]:
                units_list = MY_UNITS if tile['unit_army_id'] == army_id else THEIR_UNITS
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
    APP.logger.debug("notable_tiles:  my army_id={}\n{}".format(
        army_id, "\n".join([tilestr(tile, show_details=True) for tile in notable_tiles])))

def dist_from_enemy_hq(tile):
    return dist(OTHER_HQ[0], tile)

def my_units_by_dist():
    # todo: support multiple enemies
    units_by_dist = sorted(MY_UNITS, key=lambda tile: dist(OTHER_HQ[0], tile))
    dbg_units = ["units by distance:"]
    for unit in units_by_dist:
        dbg_units.append("{}{}: {:.1f} from enemy hq [{},{}]: {}\n".format(
            "moved " if str(unit['moved'])=='1' else "", tilestr(unit, show_details=True),
            dist_from_enemy_hq(unit), OTHER_HQ[0]['x'], OTHER_HQ[0]['y'], dict_strip_none(unit)))
    APP.logger.debug(dbg_units)
    return units_by_dist

def choose_move(player_id, army_id, game_info, tiles, players):
    my_info = players[player_id]
    # debug hack to force the algorithm to 'pick' this tile for the move,
    # building units at a castle, moving a unit, etc.
    dbg_force_tile = game_info.get('dbg_force_tile', '')   # x,y padded with zeroes, e.g. 04,14
    #todo: dbg_force_action = game_info.get('dbg_force_action', '')
    parse_map(army_id, tiles)

    # for each unit ordered by nearest to the enemy HQ
    # - if castle can be captured, capture it
    # - if village can be captured, capture it
    # - if enemy can be attacked, attack it
    # - else move randomly
    # for each castle, order by nearest to the enemy flag:
    # - create the strongest unit we can given remaining funds

    # TODO: what to move?  for now, lemmings to the slaughter
    dbg_nbrs = []
    APP.logger.debug("dbg_force_tile: {}".format(dbg_force_tile))
    for unit in my_units_by_dist():
        if str(unit['moved'])=='1': continue
        if dbg_force_tile not in ['', unit['xystr']]: continue
        unit_type, terrain_type = unit['unit_name'], unit['terrain_name']

        # don't move, just capture.  note dumb alg, e.g. unit with tiny health will still try...
        if unit['capture_remaining'] not in [None, ""] and \
           int(unit['capture_remaining']) > 0 and \
           can_capture(unit, unit, army_id) and \
           random.random() < 0.90:
            move = { 'x_coordinate': unit['x_coordinate'], 'y_coordinate': unit['y_coordinate'],
                     'movements': [], 'unit_action': 'capture' }
            return mkres(move=move)

        # randomly choose a direction to walk
        # TODO: Unicorn moves 6 when loaded
        for tile in TILES_BY_IDX.values():
            tile['seen'] = 0
            tile['path'] = None
        unit_max_move = unit['unit_type']['move']
        neighbors = unit_neighbors(unit, army_id, unit, unit_max_move, unit, [])
        if len(neighbors) == 0:
            APP.logger.debug("skip {} at {},{},{}: no walkable neighbors".format(
                unit_type, terrain_type,unit['x'], unit['y']))
            continue
        dest = random.choice(neighbors)
        dest['path'].append(dest)
        dbg_nbrs.append("walkable neighbors of {}, move={}:".format(tilestr(unit), unit_max_move))
        for nbr in sorted(neighbors, key=lambda r: r['xyloc']):
            dbg_nbrs.append("{} {} via {}".format(
                "=>" if dest['xyloc']==nbr['xyloc'] else " -",
                tilestr(nbr), pathstr(nbr['path'], show_terrain=True)))
        APP.logger.debug("\n".join(dbg_nbrs))
        move = { 'x_coordinate': unit['x_coordinate'], 'y_coordinate': unit['y_coordinate'],
                 'movements': [ { "xCoordinate": p['x'], "yCoordinate": p['y'] }
                                for p in dest['path']] }

        # usually capture open towns, castles and headquarters
        if can_capture(dest, unit, army_id) and random.random() < 0.90:
            move["unit_action"] = "capture"
        elif unit_type in ATTACKING_UNITS:
            attackmin = unit['unit_type']['attackmin']
            attackmax = unit['unit_type']['attackmax']
            attack_neighbors = [enemy_unit for enemy_unit in THEIR_UNITS
                                if attackmin <= dist(unit, enemy_unit) <= attackmax]
            random.shuffle(attack_neighbors)
            dbgmsgs = []
            dbgmsgs.append("{}: attack_neighbors: {}".format(
                tilestr(dest, show_details=True), pathstr(attack_neighbors)))
            for attack_neighbor in attack_neighbors:
                dbgmsgs.append("attack?  {}".format(tilestr(attack_neighbor, show_details=True)))
                dbg_attack_neighbor = attack_neighbor
                dbg_attack_neighbor['path'] = None
                dbgmsgs.append(repr(dict_strip_none(attack_neighbor)))
                if attack_neighbor.get('unit_army_id', '') not in ['', None, army_id] and \
                   random.random() <= 0.9:
                    move['x_coord_attack'] = attack_neighbor['x']
                    move['y_coord_attack'] = attack_neighbor['y']
                    break
            APP.logger.debug("\n".join(dbgmsgs))
        # TODO: missile attacks - need to detect enemies 2+ squares away
        return mkres(move=move)
    return build_new_units(my_info, dbg_force_tile)

def build_new_units(my_info, dbg_force_tile):
    # build new units at castles
    my_castles_by_dist = sorted(MY_CASTLES, key=dist_from_enemy_hq)
    dbg_castles = ["castles by distance:"]
    for castle in my_castles_by_dist:
        dbg_castles.append("{}: {:.1f} from enemy hq @{}: {}".format(
            tilestr(castle, show_details=True), dist_from_enemy_hq(castle),
            xyloc(OTHER_HQ[0]), dict_strip_none(castle)))
    APP.logger.debug("\n".join(dbg_castles))
    funds = int(my_info['funds'])
    for castle in my_castles_by_dist:
        if dbg_force_tile not in ['', castle['xystr']]: continue
        if castle['unit_army_id'] is None and funds >= 1000:
            unit_types = [k for k,v in UNIT_TYPES.items() if v['cost'] <= funds]
            # randomly choose the unit type
            newunit = random.choice(unit_types)
            return mkres(purchase = {
                'x_coordinate':castle['x_coordinate'], 'y_coordinate':castle['y_coordinate'],
                'unit_name':newunit})
    return mkres(end_turn=True)

class BasicNextMove(Resource):
    def post(self):
        if request.data:
            jsondata = json.loads(request.data)
            player_id = str(jsondata['botPlayerId'])
            game_info = jsondata['gameInfo']
        else:
            player_id = str(request.form['botPlayerId'])
            game_info = json.loads(request.form['gameInfo'])
        lastreq_fh=open('lastreq.json', 'w')
        lastreq_fh.write('{} "botPlayerId": {}, "gameInfo": {} {}'.format(
            "{", player_id, json.dumps(game_info), "}"))
        lastreq_fh.close()
        tiles, players = game_info['tiles'], game_info['players']
        army_id = players.get(player_id, {}).get('army_id', '')
        move = choose_move(player_id, army_id, game_info, tiles, players)
        APP.logger.debug("FLASK_DEBUG={} - move response: \n{}".format(
            os.environ['FLASK_DEBUG'], compact_json_dumps(move)))
        if DEBUG:
            response = make_response(compact_json_dumps(move))
            response.headers['content-type'] = 'application/json'
            return response
        return move

API.add_resource(Heartbeat, '/meatshields/bot/getHeartbeat')
API.add_resource(BasicNextMove, '/meatshields/bot/getNextMove')

if __name__ == '__main__':
    APP.run(debug=DEBUG)
