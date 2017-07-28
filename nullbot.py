#
# nullbot.py
#

from flask import Flask, request, json
from flask_restful import Resource, Api

app = Flask(__name__)
api = Api(app)

class Heartbeat(Resource):
    def post(self):
        return { "status": "success", "data": "OK" }

class NullNextMove(Resource):
    def post(self):
        botPlayerId = request.form['botPlayerId']
        gameInfo = json.loads(request.form['gameInfo'])
        app.logger.debug('tiles[0]: {}...'.format(gameInfo['tiles'][0]))

        # ... write your bot here ...
        
        return { "status": "success", "data": {
            "move": False,
            "purchase": False,
            "end_turn": True,
            }}

api.add_resource(Heartbeat, '/meatshields/bot/getHeartbeat')
api.add_resource(NullNextMove, '/meatshields/bot/getNextMove')

if __name__ == '__main__':
    app.run(debug=True)
