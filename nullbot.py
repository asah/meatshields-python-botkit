#
# nullbot.py
#

from flask import Flask, request, json
from flask_restful import Resource, Api

APP = Flask(__name__)
API = Api(APP)

class Heartbeat(Resource):
    def post(self):             # pylint:disable=R0201
        return { "status": "success", "data": "OK" }

class NullNextMove(Resource):
    def post(self):         # pylint:disable=R0201
        #botPlayerId = request.form['botPlayerId']
        game_info = json.loads(request.form['gameInfo'])
        APP.logger.debug('tiles[0]: {}...'.format(game_info['tiles'][0]))

        # ... write your bot here ...
        
        return { "status": "success", "data": {
            "move": False,
            "purchase": False,
            "end_turn": True,
            }}

API.add_resource(Heartbeat, '/meatshields/bot/getHeartbeat')
API.add_resource(NullNextMove, '/meatshields/bot/getNextMove')

if __name__ == '__main__':
    APP.run(debug=True)
