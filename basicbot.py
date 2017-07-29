#
# basicbot.py
#

import random, re, os
from flask import Flask, request, json, make_response
from flask_restful import Resource, Api

DEBUG = (os.environ.get('FLASK_DEBUG', '0') == '1')

app = Flask(__name__)
api = Api(app)

@app.before_request
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
WALKABLE_TERRAIN_TYPES = 'Forest,Plains,Town,Mountains,Headquarters,Castle,Road,Bridge,River,Shore'.split(',')
NORMAL_TERRAIN = set('Plains,Town,Headquarters,Castle,Road,Bridge,Shore'.split(','))
CAPTURABLE_TERRAIN = set('Headquarters,Castle,Town'.split(','))

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

def xystr(tile):
    return "{},{}".format(tile['x'],tile['y'])

def xyloc(tile):
    return tile['y']*1000 + tile['x']

def compact_json_dumps(data):
    compact_response = json.dumps(data, indent=2, sort_keys=True)
    compact_response = re.sub(r'(?m){\r?\n +', '{ ', compact_response)
    compact_response = re.sub(r'(?m)\r?\n +}', ' }', compact_response)
    if re.search(r'x_coord_attack', compact_response):
        # key sorting doesn't work nicely with x/y_coord_attack
        compact_response = re.sub(r'(?m)("x_coordinate": "[0-9]+")([, \r\n]+)("y_coord_attack": [0-9]+)', r'\3\2\1', compact_response)
    compact_response = re.sub(r'(?m)\r?\n +"(yCoord|y_coord)', r' "\1', compact_response)
    return compact_response

def pathstr(path, show_terrain=False):
    if path is None: return "{}"
    if len(path) == 0: return "[]"
    app.logger.debug("path: {}".format(path))
    return ";".join([
        (("{}@{}".format(tile['terrain_name'][0:4], xystr(tile)))
         if show_terrain else xystr(tile)) for tile in path])

def tilestr(tile, show_details=False):
    """canonical way to display a tile's location, terrain and (if present) unit.
    units are shortened to 3 chars, terrain to 4, which helps standardize formatting.
    army #1 unit names are lowercase (i.e. original form), #2 is upcase, #3 is camelcase"""
    # army #1 units are printed is like this: unic  (for unicorn)
    # army #2 units are printed is like this: Unic
    # army #3 units are printed is like this: UNic
    # army #4 units are printed is like this: UNIc
    # army #5 units are printed is like this: UNIC
    if tile['unit_name'] in [None, ""]:
        unit_name = "----"
    else:
        unit_name = tile['unit_name'][0:4]
        if tile['unit_army_id'] != '1':
            army_id = int(tile['unit_army_id'])
            if army_id > 5: raise Exception("not implemented: more than 5 armies: {}".format(army_id))
            unit_name = unit_name[0:(army_id-2)].upper() + unit_name[(army_id-2):].lower()
    return "{}@{:02d},{:02d}:{}".format(tile['terrain_name'][0:4], tile['x'], tile['y'], unit_name)

def has_unit(tile):
    return (tile.get('unit_name', '') not in [None, ''])

def xyneighbors(tiles_by_idx, tile, exclude_tiles, has_unit=None):
    """exclude_tiles is a list of tiles to exclude;
    has_unit=True: exclude empty tiles; has_unit=False: exclude filled tiles"""
    excl_xylocs = [excl['xyloc'] for excl in exclude_tiles]
    return [neighbor for neighbor in
            [tiles_by_idx.get(xyloc(tile)+1, None), tiles_by_idx.get(xyloc(tile)-1, None),
             tiles_by_idx.get(xyloc(tile)+1000, None), tiles_by_idx.get(xyloc(tile)-1000, None)]
            if neighbor is not None and neighbor['xyloc'] not in excl_xylocs and
            (has_unit is True and has_unit(neighbor)) and
            (has_unit is False and not has_unit(neighbor))]

def unit_neighbors(tiles_by_idx, tile, army_id, unit_tile, remaining_moves, prev, path):
    # counted down to the end
    # TODO: test fractional case e.g. Boulder walking through Forest
    app.logger.debug('unit_neighbors(tile={}, unit_tile={}, prev={}, path={}'.format(
        tilestr(tile), tilestr(unit_tile), tilestr(prev, show_details=True), pathstr(path)))
    if remaining_moves < 1: return [tile]
    unit_type = unit_tile['unit_type']
    # enemy tile - no neighbors allowed
    if tile['unit_army_id'] not in [None, army_id]: return []
    terrain = tile['terrain_name']
    if terrain not in WALKABLE_TERRAIN_TYPES: return []
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
    app.logger.debug('decr_moves={} vs  remaining_moves={}'.format(
        decr_moves, remaining_moves))
    if decr_moves <= 0: return []  # can't walk
    
    immediate_neighbors = [neighbor for neighbor in xyneighbors(tiles_by_idx, tile, [prev, unit_tile])
                           if neighbor['seen'] == 0 and neighbor['unit_army_id'] is None]
    app.logger.debug('neighbors of {}: {}, path:{}, moves left:{}'.format(
        tilestr(tile), pathstr(immediate_neighbors), pathstr(path), remaining_moves - decr_moves))
    res = [] if tile['xyloc'] == unit_tile['xyloc'] else [tile] 
    for immediate_neighbor in immediate_neighbors:
        newpath = path + ([tile] if tile['xyloc'] != unit_tile['xyloc'] else [])
        newres = unit_neighbors(tiles_by_idx, immediate_neighbor, army_id, unit_tile,
                                remaining_moves - decr_moves, tile, newpath)
        for r in newres:
            r['seen'] = 1
            if r['path'] is None:
                r['path'] = newpath
            res.append(r)
    return res

def dist(unit, tile):
    """distance, a (bad) approximation of travel time."""
    tx, ty = tile['x'], tile['y']
    ux, uy = unit['x'], unit['y']
    return ((ux-tx)**2 + (uy-ty)**2)**0.5

def dict_strip_none(mydict):
    return dict([(k,v) for k,v in mydict.items() if v is not None and k not in ['primary_ammo','secondary_ammo','building_team_name','unit_army_name','defense','building_army_name','deployed_unit_id','slot1_deployed_unit_id','slot2_deployed_unit_id','tile_id','unit_id','unit_team_name' ]])

def choose_move(player_id, army_id, game_info, tiles, players):
    # parsing
    my_info = players[player_id]
    funds = int(my_info['funds'])
    my_hq = None
    other_hq = []
    my_units = []
    their_units = []
    my_castles = []
    other_castles = []
    my_towns = []
    other_towns = []
    tiles_by_idx = {}
    notable_tiles = []
    for tile_ar in tiles:
        for tile in tile_ar:
            x = tile['x'] = int(tile['x_coordinate'])
            y = tile['y'] = int(tile['y_coordinate'])
            xy = tile['xyloc'] = xyloc(tile)
            tiles_by_idx[xy] = tile
            # fk it, just copy all the fields i.e. copy the whole tile
            #app.logger.debug("{}".format(dict_strip_none(tile)))
            if tile['unit_army_id'] not in ["", None]:
                units_list = my_units if tile['unit_army_id'] == army_id else their_units
                units_list.append(tile)
                tile['unit_type'] = UNIT_TYPES[tile['unit_name']]
                notable_tiles.append(tile)
            if tile['terrain_name'] == 'Headquarters':
                if tile.get('building_army_id', '') == army_id:
                    my_hq = tile
                else:
                    other_hq.append(tile)
                notable_tiles.append(tile)
            if tile['terrain_name'] == 'Castle':
                castle_list = my_castles if tile.get('building_army_id', '') == army_id else other_castles
                castle_list.append(tile)
                notable_tiles.append(tile)
            if tile['terrain_name'] == 'Town':
                town_list = my_towns if tile.get('building_army_id', '') == army_id else other_towns
                town_list.append(tile)
                
    app.logger.debug("notable_tiles:\n"+"\n".join([tilestr(tile, show_details=True) for tile in notable_tiles]))

    # for each unit ordered by nearest to the enemy HQ
    # - if castle can be captured, capture it
    # - if village can be captured, capture it
    # - if enemy can be attacked, attack it
    # - else move randomly
    # for each castle, order by nearest to the enemy flag:
    # - create the strongest unit we can given remaining funds
    dist_from_enemy_hq = lambda tile: dist(other_hq[0], tile)
    ehqx, ehqy = other_hq[0]['x'], other_hq[0]['y']
    # todo: support multiple enemies
    my_units_by_dist = sorted(my_units, key=lambda tile: dist(other_hq[0], tile))
    dbg_units = ["units by distance:"]
    for unit in my_units_by_dist:
        dbg_units.append("{}{}: {:.1f} from enemy hq [{},{}]: {}\n".format(
            "moved " if str(unit['moved'])=='1' else "", tilestr(unit, show_details=True),
            dist_from_enemy_hq(unit), ehqx, ehqy, dict_strip_none(unit)))
    app.logger.debug(dbg_units)

    # TODO: what to move?  for now, lemmings to the slaughter
    dbg_nbrs = []
    for unit in my_units_by_dist:
        if str(unit['moved'])=='1': continue
        for tile in tiles_by_idx.values():
            tile['seen'] = 0
            tile['path'] = None
        neighbors = unit_neighbors(tiles_by_idx, unit, army_id, unit, unit['unit_type']['move'], unit, [])
        if len(neighbors) == 0:
            app.logger.debug("skip {} at {},{},{}: no walkable neighbors\n".format(
                unit['unit_name'], unit['terrain_name'],unit['x'], unit['y']))
            continue
        dbg_nbrs.append("walkable neighbors of {}:".format(tilestr(unit)))
        for nbr in sorted(neighbors, key=lambda r: r['xyloc']):
            dbg_nbrs.append("- {} via {}\n".format(tilestr(nbr), pathstr(nbr['path'])))
        app.logger.debug("\n".join(dbg_nbrs))
        # randomly choose a direction to walk
        dest = random.choice(neighbors)
        dest['path'].append(dest)
        move = { 'x_coordinate': unit['x_coordinate'], 'y_coordinate': unit['y_coordinate'],
                 'movements': [ { "xCoordinate": p['x'], "yCoordinate": p['y'] } for p in dest['path']] }
        # usually capture open towns, castles and headquarters
        if (dest['terrain_name'] in CAPTURABLE_TERRAIN and dest.get('building_army_id', '') not in ['', None, army_id] and
            random.random() < 0.8):
            move["unit_action"] = "capture"
        elif unit['unit_type']['attackmin'] == 1:
            # usually attack a random neighbor
            # TODO: bugfix-- not finding neighbor...
            attack_neighbors = xyneighbors(tiles_by_idx, dest, dest['path']+[unit],
                                           has_unit=True)
            random.shuffle(attack_neighbors)
            dbgmsgs = []
            dbgmsgs.append("{}: attack_neighbors: {}".format(tilestr(dest, show_details=True), pathstr(attack_neighbors)))
            for attack_neighbor in attack_neighbors:
                dbgmsgs.append("attack?  {}".format(tilestr(attack_neighbor, show_details=True)))
                dbg_attack_neighbor = attack_neighbor
                dbg_attack_neighbor['path'] = None
                dbgmsgs.append(repr(dict_strip_none(attack_neighbor)))
                if attack_neighbor.get('unit_army_id', '') not in ['', None, army_id] and random.random() <= 0.9:
                    move['x_coord_attack'] = attack_neighbor['x']
                    move['y_coord_attack'] = attack_neighbor['y']
                    break
            app.logger.debug("\n".join(dbgmsgs))
        # TODO: missile attacks - need to detect enemies 2+ squares away
        return mkres(move=move)

    my_castles_by_dist = sorted(my_castles, key=dist_from_enemy_hq)
    dbg_castles = ["castles by distance:"]
    for castle in my_castles_by_dist:
        dbg_castles.append("{}: {:.1f} from enemy hq [{},{}]: {}\n".format(
            tilestr(castle, show_details=True), dist_from_enemy_hq(castle), ehqx, ehqy, dict_strip_none(castle)))
    app.logger.debug("\n".join(dbg_castles))

    # TODO: what to build?  For basic, just create knights... lots of knights...
    for castle in my_castles_by_dist:
        if castle['unit_army_id'] is None and funds >= 1000:
            # randomly choose for now - helps see something happen
            unit_types = [k for k,v in UNIT_TYPES.items() if v['cost'] <= funds]
            newunit = random.choice(unit_types)
            return mkres(purchase = {'x_coordinate':castle['x_coordinate'], 'y_coordinate':castle['y_coordinate'], 'unit_name':newunit})
    
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
        fh=open('lastreq.json', 'w')
        fh.write('{} "botPlayerId": {}, "gameInfo": {} {}'.format(
            "{", player_id, json.dumps(game_info), "}"))
        fh.close()
        tiles, players = game_info['tiles'], game_info['players']
        army_id = players.get(player_id, {}).get('army_id', '')
        move = choose_move(player_id, army_id, game_info, tiles, players)
        app.logger.debug("FLASK_DEBUG={} - move response: \n{}".format(
            os.environ['FLASK_DEBUG'], compact_json_dumps(move)))
        if DEBUG:
            response = make_response(compact_json_dumps(move))
            response.headers['content-type'] = 'application/json'
            return response
        return move

api.add_resource(Heartbeat, '/meatshields/bot/getHeartbeat')
api.add_resource(BasicNextMove, '/meatshields/bot/getNextMove')

if __name__ == '__main__':
    app.run(debug=DEBUG)
