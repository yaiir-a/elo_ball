# A very simple Flask Hello World app for you to get started with...

from flask import Flask, jsonify, request, make_response
from passwords import MYSQL_PASSWORD
from peewee import MySQLDatabase, Model, CharField
from json import loads, dumps
from datetime import datetime, timedelta
from itertools import chain
import requests as r

app = Flask(__name__)

### Database conenctions and things

prod_db_creds = {'host':'yaiir.mysql.pythonanywhere-services.com',
                'user':"yaiir",
                'passwd':MYSQL_PASSWORD,
                'database':"yaiir$gamerecords"}

test_db_creds = {'host':'yaiir.mysql.pythonanywhere-services.com',
                'user':"yaiir",
                'passwd':MYSQL_PASSWORD,
                'database':"yaiir$test-gamerecords"}



db = MySQLDatabase(**prod_db_creds)
test_db = MySQLDatabase(**test_db_creds)

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


### API stuff

class GameError(Exception):
    pass


class GameList(object):
    def __init__(self, days=None):
        self.games = self.get_all_games(days)

    def get_all_games(self, days):
        all_games = Games.select()
        out = []
        for row in all_games:
            result = loads(row.result)
            result['id'] = row.id
            out += [result]

        out.sort(key=lambda x: x['timestamp'])

        if days:
            date_ago = datetime.now().date() - timedelta(days=int(days))
            date_ago_iso = date_ago.isoformat()
            filtered = []
            for game in out:
                if game['timestamp'] > date_ago_iso:
                    filtered += [game]
            out = filtered
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

    def _calc_winner_change(self, sum_winners_elo, sum_losers_elo):
        Rw = 10 ** (sum_winners_elo/400)
        Rl = 10 ** (sum_losers_elo/400)
        Ew = Rw / (Rw + Rl)
        winner_change = 32 * (1 - Ew)
        return winner_change

    def add_elo(self):
        for player in self.players:
            self.players[player]['elo'] = {'current':1500, 'history':[]}
        for winners, losers, timestamp in self.games_list:
            winners_av =  sum([int(self.players[winner]['elo']['current']) for winner in winners])/len(winners)
            losers_av =  sum([int(self.players[loser]['elo']['current']) for loser in losers])/len(losers)
            winner_gain = self._calc_winner_change(winners_av, losers_av)

            for winner in winners:
                self.players[winner]['elo']['current'] += winner_gain
                self.players[winner]['elo']['history'] += [(timestamp, self.players[winner]['elo']['current'] )]

            for loser in losers:
                self.players[loser]['elo']['current'] -= winner_gain
                self.players[loser]['elo']['history'] += [(timestamp, self.players[loser]['elo']['current'] )]
        return self

    def ready_for_returning(self):
        out = []
        players = self.players
        for player in players:
            info = players[player]
            info['id'] = player
            out += [info]
        return out


class SingleGame(object):
    def __init__(self, game):
        self.validated_game(game)
        self.game = game

    def validated_game(self, body):
        all_players = body['winners'] + body['losers']
        no_duplicates = (len(set(all_players)) == len(all_players))
        all_teams = all([body['winners'], body['losers']])
        if (no_duplicates and all_teams):
            pass
        else:
            raise GameError

    def prep_create_game(self):
        try:
            self.game['timestamp']
        except KeyError:
            self.game['timestamp'] = datetime.now().isoformat()
        prepped_game = {'result':dumps(self.game), 'account_id':'default'}
        return prepped_game

    def create(self):
        prepped_game = self.prep_create_game()
        Games.create(**prepped_game)
        return self


@app.route('/')
def hello_world():
    return 'Howdy from Flask'


@app.route('/games', methods=['GET', 'POST'])
def games():
    if request.method == 'POST':
        body = request.get_json()
        try:
            SingleGame(body).create()
            return jsonify(GameList().games)
        except GameError:
            return make_response(jsonify({'error':'check the teams reported'}), 400)
        except:
            return make_response(jsonify({'error':'server fuckup'}), 500)
    else:
        days = request.args.get('days')
        return jsonify(GameList(days).games)


@app.route('/games/<game_id>', methods=['DELETE'])
def delete_games(game_id):
    # TODO move this into SingleGame(), can then return metadata of deleted game
    Games.get( Games.id == game_id ).delete_instance()
    return jsonify(GameList().games)


@app.route('/players', methods=['GET'])
def get_players():
    game_list = GameList()
    player_list = PlayerList(game_list).add_records().add_elo().ready_for_returning()
    return jsonify(player_list)




##### SLACK INTEGRATION - should be separate but keeping together for python anywhere limitations
from re import findall, sub
from tabulate import tabulate
import pandas as pd

class SlackSingleGame(object):
    def __init__(self, winners, losers, timestamp, game_id=None):
        self.winners = winners
        self.losers = losers
        self.timestamp = timestamp
        self.game_id = game_id

    def _dictify(self):
        out = {
            'winners': self.winners,
            'losers': self.losers,
            'timestamp': self.timestamp,
            'id': self.game_id
            }
        return out

    def create(self):
        r.post('https://yaiir.pythonanywhere.com/games', json=self._dictify())
        return self

    def delete(self):
        r.delete('https://yaiir.pythonanywhere.com/games/{}'.format(self.game_id))
        return self

    def pprint(self):
        return self._dictify()

class SlackPlayerList(object):
    def __init__(self, days=None):
        raw = r.get('https://yaiir.pythonanywhere.com/players').json()
        raw.sort(key=lambda x: x['record']['losses'])
        raw.sort(key=lambda x: x['record']['wins'], reverse=True)
        raw.sort(key=lambda x: x['elo']['current'], reverse=True)
        self.players = raw

    def filter_player_list(self, user_ids):
        return [row for row in self.players if (row['id'] in user_ids)]

    def _prep_pprint(self, users=None):
        out = [['Player', 'Elo', 'Diff', 'Wins', 'Losses']]

        for record in self.players:
            name = self._replace_mentions_with_username(record['id'])
            elo, wins, losses = round(record['elo']['current']), record['record']['wins'], record['record']['losses']
            try:
                if record['id'] in users:
                    last_game_ts = record['elo']['history'][-1][0]
                    history = record['elo']['history']
                    first_game_of_set = min([i for i, (ts, elo) in enumerate(history) if (ts == last_game_ts)])
                    prev_game_ts, prev_game_elo = record['elo']['history'][first_game_of_set - 1]
                    diff = elo - prev_game_elo
                    if prev_game_ts == last_game_ts:
                        diff = elo - 1500
                    diff = round(diff)
                else:
                    diff = 0
            except TypeError:
                diff = 0
            out += [[name, elo, diff, wins, losses]]
        return out

    def pprint(self, users=None):
        out = self._prep_pprint(users)
        tabulated = tabulate(out, tablefmt='simple', headers='firstrow')
        out = {
            "response_type": "in_channel",
            "text": '```{}```'.format(tabulated)
        }
        return out

    def _replace_mentions_with_username(self, text):
        return sub('\<(.*?)\|', '', text).replace('>', '')

class SlackGameList(object):
    def __init__(self):
        self.raw_games = r.get('https://yaiir.pythonanywhere.com/games').json()
        self.raw_games.sort(key=lambda x: x['timestamp'], reverse=True)
        self.raw_games = self.raw_games[:30]
        self.games = [SlackSingleGame(game['winners'], game['losers'], game['timestamp'], game['id']) for game in self.raw_games]

    def delete(self, game_id):
        for game in self.games:

            if str(game.game_id) == str(game_id):
                game.delete()
                return game.pprint()

    def pprint(self, text='all the games'):
        attachments = []
        for game in self.games:
            attachments += [{
                    "title": '{} beat {} at {}'.format(game.winners, game.losers, game.timestamp),
                    "callback_id": "delete_game",
                    "attachment_type": "default",
                    "actions": [
                        {
                            "name": "delete",
                            "text": "Delete Game",
                            "type": "button",
                            "value": game.game_id
                        }
                    ]
                }]
        out =   {
        "text": 'all the games',
        "response_type": "in_channel",
        "attachments": attachments
        }
        return out

class SlackChanges(object):
    def __init__(self):
        raw_data = r.get('https://yaiir.pythonanywhere.com/players').json()
        df = pd.DataFrame(raw_data)

        def munge_history(row):
            hist = row['history']
            hist_dict = {time: elo for time, elo in hist}
            return hist_dict

        df ['history'] = df['elo'].apply(munge_history)
        df = df.set_index('id')
        df = pd.DataFrame({name: df.loc[name]['history'] for name in df.index}).sort_index()
        df = df.fillna(value=1500, limit=1)
        df = df.fillna(method='ffill')
        df.index = pd.to_datetime(df.index)
        tg = pd.Grouper(freq='w')
        df = df.groupby(tg).last().sort_index(ascending=False)
        df.index = df.index.strftime(date_format = '%Y-%m-%d')
        self.df = df

    def _prep_pprint(self):
        df = self.df
        df = df.diff(-1).head(6).round(1).transpose().sort_values(df.index[0], ascending=False)
        df = df.head(3).append(df.tail(3))
        df['Player'] = df.index
        df['Player'] = df['Player'].apply(lambda x: self._replace_mentions_with_username(x))
        df = df[['Player'] + df.columns.tolist()[:-1]]
        headers = ['Player', 'Current'] + list(df.columns)[2:]
        table = df.values.tolist()
        return [headers] + table

    def _replace_mentions_with_username(self, text):
        return sub('\<(.*?)\|', '', text).replace('>', '')


    def pprint(self):
        out = self._prep_pprint()
        tabulated = tabulate(out, tablefmt='simple', headers='firstrow')
        out = {
            "response_type": "in_channel",
            "text": '```{}```'.format(tabulated)
        }
        return out

class SlackCommand(object):
    def __init__(self, request):
        self.request = request
        self.raw_text = request.form['text']
        self.cleaned_text = request.form['text'].replace(' ', '').replace('beat', '1-0')
        self.com_type = self._calc_type()
        self.users = self._extract_all_users_from_text(self.cleaned_text)
        if self.com_type == 'report':
            self.report = self._clean_report()

    def _calc_type(self):
        if '-' in self.cleaned_text:
            return 'report'
        elif 'game' in self.cleaned_text:
            return 'gamelist'
        elif 'changes' in self.cleaned_text:
            return 'changes'
        else:
            try:
                self.result_days = int(self.cleaned_text)
            except ValueError:
                self.result_days = 30  # Default days in Slack
            if self.cleaned_text == '':
                self.result_days = None
            return 'playerlist'

    def _clean_report(self):
        a, b = self.cleaned_text.split('-')
        team_a, wins_a = a[:-1], int(a[-1])
        team_b, wins_b = b[1:], int(b[0])
        out = {
            'a':{'members':self._extract_all_users_from_text(team_a), 'wins':wins_a},
            'b':{'members':self._extract_all_users_from_text(team_b), 'wins':wins_b}
        }
        return out

    def _extract_all_users_from_text(self, text):
        list_of_users = findall('\<(.*?)\>', text)
        list_with_tags = ['<{}>'.format(user) for user in list_of_users]
        return list_with_tags

    def create(self):
        report = self.report
        timestamp = datetime.now().isoformat()

        for _ in range(report['a']['wins']):
            winners, losers = report['a']['members'], report['b']['members']
            SlackSingleGame(winners, losers, timestamp).create()

        for _ in range(report['b']['wins']):
            winners, losers = report['b']['members'], report['a']['members']
            SlackSingleGame(winners, losers, timestamp).create()
        return self


@app.route("/slack", methods=['POST'])
def slack():
    command = SlackCommand(request)
    if command.com_type == 'report':
        command.create()
        out = SlackPlayerList().pprint(command.users)
        return jsonify(out)
    if command.com_type == 'gamelist':
        out = SlackGameList().pprint()
        return jsonify(out)
    if command.com_type == 'changes':
        out = SlackChanges().pprint()
        return jsonify(out)
    if command.com_type == 'playerlist':
        out = SlackPlayerList(days=command.result_days).pprint()
        return jsonify(out)


@app.route("/slack/actions", methods=['GET', 'POST'])
def slack_action():
    payload = loads(request.form['payload'])
    game_id = payload['actions'][0]['value']
    deleted_metadata = SlackGameList().delete(game_id)
    return jsonify({'deleted game':deleted_metadata})