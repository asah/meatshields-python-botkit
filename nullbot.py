#
# ms1.py
#
# Skeleton API server for writing meatshields bots:
# see https://meatshields.com/createBotGuide.php
#
# 1. install Flask-Restful on a fresh Ubuntu 16.04 install:
# sudo apt-get update; sudo apt-get upgrade
# sudo apt-get install python3-pip
# pip3 install flask flask-restful
# 
# 2. run the bot server
# ./run.sh
#
# 3. in a separate window, test the heartbeat interface:
# ./test_heartbeat.sh
# OK
#
# 4. in a separate window, test the nextmove interface:
# ./test_nextmove.sh
# {
#     "status": "success",
#     "data": {
#         "purchase": false,
#         "end_turn": true,
#         "move": false
#     }
# }
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
