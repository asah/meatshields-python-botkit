#
# basicbot.py
#

from flask import Flask, request, json
from flask_restful import Resource, Api

app = Flask(__name__)
api = Api(app)

class Heartbeat(Resource):
    def post(self):
        return { "status": "success", "data": "OK" }

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

def unit_neighbors(tiles_by_idx, tile, army_id, unit_tile, remaining_moves):
    # counted down to the end
    if remaining_move == 0: return []
    unit_type = unit_tile['unit_type']
    # enemy tile - no neighbors allowed
    if tile['unit_army_id'] not in [None, army_id]: return []
    terrain = tile['terrain_name']
    if terrain not in WALKABLE_TERRAIN_TYPES: return []
    new_remaining_moves = remaining_moves
    if unit_type == 'Knight':
        if terrain in NORMAL_TERRAIN: new_remaining_moves -= 1
        elif terrain in ['Forest','River','Mountains']: new_remaining_moves -= 2
    elif unit_type in set(['Archer','Ninja']):
        remaining_moves -= 2
    elif unit_type == 'Mount':
        if terrain in ['Road','Bridge']: new_remaining_moves -= 1
        elif terrain in NORMAL_TERRAIN: new_remaining_moves -= 2
    else: # normal walking units
        if terrain in NORMAL_TERRAIN: new_remaining_moves -= 1
        elif terrain == 'Forest': new_remaining_moves -= 2
    if new_remaining_moves == remaining_moves: return []  # can't walk
    
    tx, ty = tile['x'], tile['y']
    immediate_neighbors = [neighbor for neighbor in [
        tiles_by_idx.get(ty*1000+tx+1, None), tiles_by_idx.get(ty*1000+tx-1, None),
        tiles_by_idx.get((ty+1)*1000+tx+1, None), tiles_by_idx.get((ty-1)*1000+tx-1, None)]
                 if neighbor is not None]
    res = []
    for immediate_neighbor in immediate_neighbors:
        res += unit_neighbors(tiles_by_idx, immediate_neighbor, army_id, unit_tile, remaining_moves)
    return res

def dist(unit, tile):
    """distance, a (bad) approximation of travel time."""
    tx, ty = tile['x'], tile['y']
    ux, uy = unit['x'], unit['y']
    return ((ux-tx)**2 + (uy-ty)**2)**0.5

def dict_strip_none(mydict):
    return dict([(k,v) for k,v in mydict.items() if v is not None])

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
            print("{}".format(dict_strip_none(tile)))
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
        dbg_ubd += "{} at {},{}: {:.1f} from enemy hq [{},{}]\n".format(
            unit['unit_name'], unit['x'], unit['y'], dist_from_enemy_hq(unit), ehqx, ehqy)
        # TODO: what to move and where?

    my_castles_by_dist = sorted(my_castles, key=dist_from_enemy_hq)
    dbg_cbd = "castles by distance:\n"
    for castle in my_castles_by_dist:
        dbg_cbd += "castle at {},{}: {:.1f} from enemy hq [{},{}]: {}\n".format(
            castle['x'], castle['y'], dist_from_enemy_hq(castle), ehqx, ehqy, dict_strip_none(castle))
        # TODO: what to build?        
    app.logger.debug(dbg_cbd)

    for castle in my_castles_by_dist:
        if castle['unit_army_id'] is None and funds > 0:
            return { "status": "success", "data": {
                "move": False, "end_turn": False,
                "purchase": {'x_coordinate':castle['x_coordinate'], 'y_coordinate':castle['y_coordinate'], 'unit_name':'Knight'}}}
    
    return { "status": "success", "data": {
        "move": False,
        "purchase": False,
        "end_turn": True,
    }}

class BasicNextMove(Resource):
    def post(self):
        if request.data:
            jsondata = json.loads(request.data)
            player_id = str(jsondata['botPlayerId'])
            game_info = jsondata['gameInfo']
        else:
            player_id = str(request.form['botPlayerId'])
            game_info = json.loads(request.form['gameInfo'])
        tiles, players = game_info['tiles'], game_info['players']
        #app.logger.debug(json.dumps(tiles))
        army_id = players.get(player_id, {}).get('army_id', '')
        move = choose_move(player_id, army_id, game_info, tiles, players)
        app.logger.debug(move)
        return move

api.add_resource(Heartbeat, '/meatshields/bot/getHeartbeat')
api.add_resource(BasicNextMove, '/meatshields/bot/getNextMove')

if __name__ == '__main__':
    app.run(debug=True)
