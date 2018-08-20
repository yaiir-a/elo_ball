# A very simple Flask Hello World app for you to get started with...

from flask import Flask, jsonify, request, make_response
from passwords import MYSQL_PASSWORD
from peewee import MySQLDatabase, Model, CharField
from json import loads, dumps
from datetime import datetime


app = Flask(__name__)


db = MySQLDatabase(host='yaiir.mysql.pythonanywhere-services.com',
                     user="yaiir",
                     passwd=MYSQL_PASSWORD,
                     database="yaiir$gamerecords")

class BaseModel(Model):
    class Meta:
        database = db

class Games(BaseModel):
    result = CharField()


class GameError(Exception):
    pass


def validated_players(body):
    all_players = body['winners'] + body['losers']
    if len(set(all_players)) == len(all_players):
        pass
    else:
        raise GameError

def get_all_games():
    all_games = Games.select()
    out = []
    for row in all_games:
        result = loads(row.result)
        result['id'] = row.id
        out += [result]
    return out

def prep_create_game(body):
    body['timestamp'] = datetime.now().isoformat()
    prepped_game = {'result':dumps(body)}
    return prepped_game


@app.route('/')
def hello_world():
    return 'Hello from Flask!'


@app.route('/games', methods=['GET', 'POST'])
def games():
    if request.method == 'POST':
        body = request.get_json()
        try:
            validated_players(body)
            prepped_game = prep_create_game(body)
            Games.create(**prepped_game)
            out = get_all_games()
            return jsonify(out)
        except GameError:
            return make_response(jsonify({'error':'duplicate players submitted'}), 400)
        except:
            return make_response(jsonify({'error':'server fuckup'}), 500)
    elif request.method == 'DELETE':
        return
    else:
        out = get_all_games()
        return jsonify(out)

@app.route('/games/<game_id>', methods=['DELETE'])
def delete_games(game_id):
    Games.get( Games.id == game_id ).delete_instance()
    out = get_all_games()
    return jsonify(out)


