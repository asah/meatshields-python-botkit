from flask import Flask
from flask_restful import Resource, Api

APP = Flask(__name__)
API = Api(APP)

class HelloWorld(Resource):
    def get(self):  # pylint:disable=R0201
        return {'hello': 'world'}

API.add_resource(HelloWorld, '/')

if __name__ == '__main__':
    APP.run(debug=True)
