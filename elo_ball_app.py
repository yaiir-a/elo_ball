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

@app.before_request
def _db_connect():
    db.connect()

@app.teardown_request
def _db_close(exc):
    if not db.is_closed():
        db.close()

class BaseModel(Model):
    class Meta:
        database = db

class Games(BaseModel):
    result = CharField()
    account_id = CharField()


class GameError(Exception):
    pass


class GameList(object):
    def __init__(self):
        self.games = self.get_all_games()

    def get_all_games(self):
        all_games = Games.select()
        out = []
        for row in all_games:
            result = loads(row.result)
            result['id'] = row.id
            out += [result]

        out.sort(key=lambda x: x['timestamp'])
        return out


class PlayerList(object):
    def __init__(self, games):
        self.games = games
        player_set = chain(*[game['winners'] + game['losers'] for game in games.games])
        self.players = {player:dict() for player in player_set}
        self.games_list = self._games_list()

    def _games_list(self):
        games_list = []
        for game in self.games.games:
            games_list += [[game['winners'], game['losers'], game['timestamp']]]
        return games_list

    def add_records(self):
        for player in self.players:
            self.players[player]['record'] = {'wins':0, 'losses':0}

        for winners, losers, timestamp in self.games_list:
            for player in winners:
                self.players[player]['record']['wins'] += 1
            for player in losers:
                self.players[player]['record']['losses'] += 1
        return self

    def add_rating(self):
        for player in self.players:
            self.players[player]['elo'] = {'current':1500, 'history':[]}

        for winners, losers, timestamp in self.games_list:
            for player in winners:
                self.players[player]['elo']['current'] += 100
                self.players[player]['elo']['history'] += [{timestamp: self.players[player]['elo']['current']}]
            for player in losers:
                self.players[player]['elo']['current'] -= 100
                self.players[player]['elo']['history'] += [{timestamp: self.players[player]['elo']['current']}]
        return self


def validated_game(body):
    all_players = body['winners'] + body['losers']
    no_duplicates = (len(set(all_players)) == len(all_players))
    all_teams = all([body['winners'], body['losers']])
    if (no_duplicates and all_teams):
        pass
    else:
        raise GameError

def prep_create_game(body):
    try:
        body['timestamp']
    except KeyError:
        body['timestamp'] = datetime.now().isoformat()
    prepped_game = {'result':dumps(body), 'account_id':'default'}
    return prepped_game


@app.route('/')
def hello_world():
    return 'Howdy from Flask'


@app.route('/games', methods=['GET', 'POST'])
def games():
    if request.method == 'POST':
        body = request.get_json()
        try:
            validated_game(body)
            prepped_game = prep_create_game(body)
            Games.create(**prepped_game)
            return jsonify(GameList().games)
        except GameError:
            return make_response(jsonify({'error':'check the teams reported'}), 400)
        except:
            return make_response(jsonify({'error':'server fuckup'}), 500)
    else:
        return jsonify(GameList().games)


@app.route('/games/<game_id>', methods=['DELETE'])
def delete_games(game_id):
    Games.get( Games.id == game_id ).delete_instance()
    return jsonify(GameList().games)


@app.route('/players', methods=['GET'])
def get_players():
    game_list = GameList()
    player_list = PlayerList(game_list).add_records().add_rating()

    return jsonify(player_list.players)


##### SLACK INTEGRATION - should be separate but keeping together for python anywhere limitations
from re import findall, sub

def extract_all_users_from_text(text):
    list_of_users = findall('\<(.*?)\>', text)
    list_with_tags = ['<{}>'.format(user) for user in list_of_users]
    return list_with_tags

def slack_create_single(winners, losers, timestamp):
    out = {
            'winners': winners,
            'losers': losers,
            'timestamp': timestamp
        }
    r.post('https://yaiir.pythonanywhere.com/games', json=out)

def slack_handle_create(report):
    timestamp = datetime.now().isoformat()

    for _ in range(report['a']['wins']):
        slack_create_single(report['a']['members'], report['b']['members'], timestamp)

    for _ in range(report['b']['wins']):
        slack_create_single(report['b']['members'], report['a']['members'], timestamp)



def slack_handle_results(text=None):
    players = r.get('https://yaiir.pythonanywhere.com/players').json()
    flattened = slack_flatten_records(players)
    if text:
        involved = extract_all_users_from_text(text)
        flattened = [(name, wins, losses) for (name, wins, losses) in flattened if (name in involved)]
    sorted_recs = slack_sort_flattened_records(flattened)
    prepped_for_printing = slack_prep_records_for_printing(sorted_recs)
    return prepped_for_printing

def slack_flatten_records(players):
    out = []
    for name, info in players.items():
        out += [(name, info['record']['wins'], info['record']['losses'])]
    return out

def slack_sort_flattened_records(records_flat):
    records_flat.sort(key=lambda x: x[2])
    records_flat.sort(key=lambda x: x[1], reverse=True)
    return records_flat

def slack_prep_records_for_printing(records_flat):
    out = '{} | {} | {}\n'.format('Wins', 'Losses', 'Player')
    for name, wins, losses in records_flat:
        name = slack_replace_mentions_with_username(name)
        out += '{}       | {}          | {}\n'.format(wins, losses, name)
    out = {
        "response_type": "in_channel",
        "text": out
    }
    return out

def slack_prep_games_for_printing(text='all the games'):
    games = r.get('https://yaiir.pythonanywhere.com/games').json()
    attachments = []
    for game in games[::-1]:
        attachments += [{
                "title": '{} beat {} at {}'.format(game['winners'], game['losers'], game['timestamp']),
                "callback_id": "delete_game",
                "attachment_type": "default",
                "actions": [
                    {
                        "name": "delete",
                        "text": "Delete Game",
                        "type": "button",
                        "value": game['id']
                    }
                ]
            }]
    out =   {
        "text": text,
        "response_type": "in_channel",
        "attachments": attachments
        }
    return out

def slack_replace_mentions_with_username(text):
    return sub('\<(.*?)\|', '', text).replace('>', '')

def slack_clean_input(text):
    a, b = text.replace(' ', '').replace('beat', '1-0').split('-')
    team_a, wins_a = a[:-1], int(a[-1])
    team_b, wins_b = b[1:], int(b[0])
    out = {
        'a':{'members':extract_all_users_from_text(team_a), 'wins':wins_a},
        'b':{'members':extract_all_users_from_text(team_b), 'wins':wins_b}
    }
    return out

@app.route("/slack", methods=['POST'])
def slack():
    text = request.form['text']
    try:
        report = slack_clean_input(text)
        slack_handle_create(report)
        out = slack_handle_results(text)
        return jsonify(out)
    except ValueError:
        if 'game' in text:
            out = slack_prep_games_for_printing()
            return jsonify(out)
        out = slack_handle_results()
        return jsonify(out)

@app.route("/slack/actions", methods=['GET', 'POST'])
def slack_action():
    payload = loads(request.form['payload'])
    game_id = payload['actions'][0]['value']
    r.delete('http://yaiir.pythonanywhere.com/games/' + game_id)
    text = 'deleted game: {}'.format(game_id)
    out = slack_prep_games_for_printing(text)
    return jsonify(out)