# A very simple Flask Hello World app for you to get started with...

from flask import Flask, jsonify, request, make_response

app = Flask(__name__)



class GameError(Exception):
    pass

all_games = [
    {'winners': ['1','2'], 'losers':['3','4']},
    {'winners': ['1', '2'], 'losers':['3','5']},
    {'winners': ['1'], 'losers':['3']}
    ]


def validated_players(body):
    all_players = body['winners'] + body['losers']
    if len(set(all_players)) == len(all_players):
        pass
    else:
        raise GameError



@app.route('/')
def hello_world():
    return 'Hello from Flask!'


@app.route('/games', methods=['GET', 'POST'])
def games():
    global all_games
    if request.method == 'POST':
        body = request.get_json()
        try:
            validated_players(body)
            all_games += [body]
            return jsonify(all_games)
        except GameError:
            return make_response(jsonify({'error':'duplicate players submitted'}), 400)
    else:
        return jsonify(all_games)


