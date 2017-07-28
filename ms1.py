#
# ms1.py
#
# Skeleton API server for writing meatshields bots:
# see https://meatshields.com/createBotGuide.php
#

from flask import Flask, request
from flask_restful import Resource, Api

app = Flask(__name__)
api = Api(app)

class Heartbeat(Resource):
    def post(self):
        return "OK"

class NullNextMove(Resource):
    def post(self):
        json = request.get_json(force=True)
        app.logger.debug(json)

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
