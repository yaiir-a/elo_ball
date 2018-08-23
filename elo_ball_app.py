# A very simple Flask Hello World app for you to get started with...

from flask import Flask, jsonify, request, make_response
from passwords import MYSQL_PASSWORD
from peewee import MySQLDatabase, Model, CharField
from json import loads, dumps
from datetime import datetime
from itertools import chain
import requests as r

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
    return 'Howdy from Flask'


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
    else:
        out = get_all_games()
        return jsonify(out)


@app.route('/games/<game_id>', methods=['DELETE'])
def delete_games(game_id):
    Games.get( Games.id == game_id ).delete_instance()
    out = get_all_games()
    return jsonify(out)


@app.route('/players', methods=['GET'])
def get_players():
    all_games = get_all_games()
    all_games = [game for game in all_games if 'timestamp' in game] ## TODO: make sure timestamp is present when creating/tidyup db
    player_set = set(chain(*[game['winners'] + game['losers'] for game in all_games]))
    player_records = {player:{'record':{'wins':0, 'losses':0}} for player in player_set}

    for game in all_games:
        winners, losers = game['winners'], game['losers']
        for player in winners:
            player_records[player]['record']['wins'] += 1
        for player in losers:
            player_records[player]['record']['losses'] += 1

    return jsonify(player_records)


##### SLACK INTEGRATION - should be separate but keeping together for python anywhere limitations
from re import findall, sub

def extract_all_users_from_text(text):
    list_of_users = findall('\<(.*?)\>', text)
    list_with_tags = ['<{}>'.format(user) for user in list_of_users]
    return list_with_tags

def slack_handle_create(text):
    winners, losers = text.split('beat')
    out = {
        'winners': extract_all_users_from_text(winners),
        'losers': extract_all_users_from_text(losers)
    }
    #TODO catch/handle errors
    out = r.post('https://yaiir.pythonanywhere.com/games', json=out).json()

def slack_handle_results():
    players = r.get('https://yaiir.pythonanywhere.com/players').json()
    flattened = slack_flatten_records(players)
    sorted_recs = slack_sort_flattened_records(flattened)
    prepped_for_printing = slack_prep_records_for_printing(sorted_recs)
    return prepped_for_printing

def slack_flatten_records(players):
    out = []
    for name, info in players.items():
        out += [(name, info['record']['wins'], info['record']['losses'])]
    return out

def slack_sort_flattened_records(records_flat):
    records_flat.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return records_flat

def slack_prep_records_for_printing(records_flat):
    out = '{} | {} | {}\n'.format('Wins', 'Losses', 'Player')
    for name, wins, losses in records_flat:
        name = name[name.find('|') + 1 : name.find('>')]
        out += '{}       | {}          | {}\n'.format(wins, losses, name)
    out = {
        "response_type": "in_channel",
        "text": out
    }
    return out

def slack_prep_games_for_printing():
    games = r.get('https://yaiir.pythonanywhere.com/games').json()
    text = ''
    for game in games:
        text += '{} beat {}. ID:{}\n'.format(game['winners'], game['losers'], game['id'])
    text = slack_replace_mentions_with_username(text)
    out = {
        "response_type": "in_channel",
        "text": text
        }
    return out

def slack_replace_mentions_with_username(text):
    return sub('\<(.*?)\|', '', text).replace('>', '')


@app.route("/slack", methods=['POST'])
def slack():
    text = request.form['text']
    if 'beat' in text:
        out = slack_handle_create(text)
    if 'game' in text:
        out = slack_prep_games_for_printing()
        return jsonify(out)
    out = slack_handle_results()
    return jsonify(out)