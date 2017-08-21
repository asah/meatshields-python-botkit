#!/usr/bin/env python3
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
import os, random
import basicbot_lib
from flask import Flask, request, json, make_response
from flask_restful import Resource, Api

APP = Flask(__name__)
API = Api(APP)
DBGPRINT = APP.logger.debug

@APP.before_request
def set_random_seed():
    bblib.set_random_seed()

class Heartbeat(Resource):
    def post(self):
        return { "status": "success", "data": "OK" }

class BasicNextMove(Resource):
    def post(self):
        if request.data:
            jsondata = json.loads(request.data)
            player_id = str(jsondata['botPlayerId'])
            game_info = jsondata['gameInfo']
        else:
            player_id = str(request.form['botPlayerId'])
            game_info = json.loads(request.form['gameInfo'])
        move = basicbot_lib.select_next_move(player_id, game_info)
        if DEBUG:
            DBGPRINT("move response: \n{}".format(basicbot_lib.compact_json_dumps(move)))
            response = make_response(basicbot_lib.compact_json_dumps(move))
            response.headers['content-type'] = 'application/json'
        else:
            response = move
        return response

API.add_resource(Heartbeat, '/meatshields/bot/getHeartbeat')
API.add_resource(BasicNextMove, '/meatshields/bot/getNextMove')

DEBUG = (os.environ.get('FLASK_DEBUG', '0') == '1')

if __name__ == '__main__':
    APP.run(debug=DEBUG)
