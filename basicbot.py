#
# basicbot.py
#

from flask import Flask, request, json
from flask_restful import Resource, Api
import random

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
WALKABLE_TERRAIN_TYPES = 'Forest,Plains,Town,Mountains,Headquarters,Castle,Road,Bridge,River'.split(',')
NORMAL_TERRAIN = set('Plains,Town,Headquarters,Castle,Road,Bridge'.split(','))

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

def pathstr(path):
    return "{}" if path is None else ";".join([xystr(p) for p in path]) 

def unit_neighbors(tiles_by_idx, tile, army_id, unit_tile, remaining_moves, prev, path):
    # counted down to the end
    # TODO: test fractional case e.g. Boulder walking through Forest
    if remaining_moves < 1: return [tile]
    unit_type = unit_tile['unit_type']
    # enemy tile - no neighbors allowed
    app.logger.debug('army_id@{}: {}'.format(xystr(tile), tile['unit_army_id']))
    if tile['unit_army_id'] not in [None, army_id]: return []
    terrain = tile['terrain_name']
    app.logger.debug('terrain@{}: {}'.format(xystr(tile), terrain))
    if terrain not in WALKABLE_TERRAIN_TYPES: return []
    #app.logger.debug("{}".format(dict_strip_none(tile)))
    decr_moves = 0
    if unit_type == 'Knight':
        if terrain in NORMAL_TERRAIN: decr_moves = 1
        elif terrain in ['Forest','River','Mountains']: decr_moves = 2
    elif unit_type in ['Archer','Ninja']:
        decr_moves = 2
    elif unit_type == 'Mount':
        if terrain in ['Road','Bridge']: decr_moves = 1
        elif terrain in NORMAL_TERRAIN: decr_moves = 2
    else: # normal walking units
        if terrain in NORMAL_TERRAIN: decr_moves = 1
        elif terrain == 'Forest': decr_moves = 2
    app.logger.debug('decr_moves={} vs  remaining_moves={}'.format(
        decr_moves, remaining_moves))
    if decr_moves <= 0: return []  # can't walk
    
    tx, ty = tile['x'], tile['y']
    immediate_neighbors = [neighbor for neighbor in [
        tiles_by_idx.get(xyloc(tile)+1, None), tiles_by_idx.get(xyloc(tile)-1, None),
        tiles_by_idx.get(xyloc(tile)+1000, None), tiles_by_idx.get(xyloc(tile)-1000, None)]
                           if neighbor is not None and neighbor['seen'] == 0 and
                           neighbor['unit_army_id'] is None and
                           xyloc(neighbor) != xyloc(prev) and
                           xyloc(neighbor) != xyloc(unit_tile)
    ]
    app.logger.debug('neighbors of {},{},{}: {} - {} left - path:{}'.format(
        tile['terrain_name'], tx, ty, "  ".join(["{}:{},{}".format(
            t['terrain_name'],t['x'],t['y']) for t in immediate_neighbors]),
        remaining_moves - decr_moves, pathstr(path)))
    res = [] if xyloc(tile) == xyloc(unit_tile) else [tile] 
    for immediate_neighbor in immediate_neighbors:
        newpath = path + ([tile] if xyloc(tile) != xyloc(unit_tile) else [])
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
    for tile_ar in tiles:
        for tile in tile_ar:
            x = tile['x'] = int(tile['x_coordinate'])
            y = tile['y'] = int(tile['y_coordinate'])
            tiles_by_idx[y*1000 + x] = tile
            # fk it, just copy all the fields i.e. copy the whole tile
            #app.logger.debug("{}".format(dict_strip_none(tile)))
            if tile['unit_army_id'] is not None:
                units_list = my_units if tile['unit_army_id'] == army_id else their_units
                units_list.append(tile)
                tile['unit_type'] = UNIT_TYPES[tile['unit_name']]
            if tile['terrain_name'] == 'Headquarters':
                if tile.get('building_army_id', '') == army_id:
                    my_hq = tile
                else:
                    other_hq.append(tile)
            if tile['terrain_name'] == 'Castle':
                castle_list = my_castles if tile.get('building_army_id', '') == army_id else other_castles
                castle_list.append(tile)
            if tile['terrain_name'] == 'Town':
                town_list = my_towns if tile.get('building_army_id', '') == army_id else other_towns
                town_list.append(tile)

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
    dbg_ubd = "units by distance:\n"
    for unit in my_units_by_dist:
        dbg_ubd += "{}{} at {},{}: {:.1f} from enemy hq [{},{}]: {}\n".format(
            "moved " if str(unit['moved'])=='1' else "", unit['unit_name'],
            unit['x'], unit['y'], dist_from_enemy_hq(unit), ehqx, ehqy, dict_strip_none(unit))
            
    app.logger.debug(dbg_ubd)

    # TODO: what to move?  for now, lemmings to the slaughter
    dbg_nbr = ""
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
        dbg_nbr += "walkable neighbors of {} at {},{},{}:\n".format(unit['unit_name'], unit['terrain_name'],unit['x'], unit['y'])
        for nbr in sorted(neighbors, key=lambda r: r['y']*1000+r['x']):
            dbg_nbr += "- {} at {},{} via {}\n".format(nbr['terrain_name'], nbr['x'], nbr['y'], pathstr(nbr['path']))
        app.logger.debug(dbg_nbr)
        # TODO: for now, randomness!
        dest = random.choice(neighbors)
        return mkres(move= { 'x_coordinate': unit['x_coordinate'], 'y_coordinate': unit['y_coordinate'],
                             #,"unit_action": "capture"
                             'movements': [ { "xCoordinate": p['x'], "yCoordinate": p['y'] } for p in dest['path']] })

    my_castles_by_dist = sorted(my_castles, key=dist_from_enemy_hq)
    dbg_cbd = "castles by distance:\n"
    for castle in my_castles_by_dist:
        dbg_cbd += "castle at {},{}: {:.1f} from enemy hq [{},{}]: {}\n".format(
            castle['x'], castle['y'], dist_from_enemy_hq(castle), ehqx, ehqy, dict_strip_none(castle))
    app.logger.debug(dbg_cbd)

    # TODO: what to build?  For basic, just create knights... lots of knights...
    for castle in my_castles_by_dist:
        if castle['unit_army_id'] is None and funds > 0:
            # randomly choose for now - helps see something happen
            newunit = "Knight" if random.random() < 0.5 else "Unicorn"
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
        fh=open('reqlog', 'w')
        fh.write('{} "botPlayerId": {}, "gameInfo": {} {}'.format(
            "{", player_id, json.dumps(game_info), "}"))
        fh.close()
        tiles, players = game_info['tiles'], game_info['players']
        #app.logger.debug(json.dumps(tiles))
        army_id = players.get(player_id, {}).get('army_id', '')
        move = choose_move(player_id, army_id, game_info, tiles, players)
        app.logger.debug("res: {}".format(move))
        return move

api.add_resource(Heartbeat, '/meatshields/bot/getHeartbeat')
api.add_resource(BasicNextMove, '/meatshields/bot/getNextMove')

if __name__ == '__main__':
    app.run(debug=True)
