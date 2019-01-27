import elo_ball_app as e
import config
import requests as r


def url(endpoint):
    return config.base_url + endpoint


def test_get_games():
    print(r.get(url('/games')).status_code)

def test_SingleGame():
    payload = {
        'losers':['testgame'],
        'winners':['suckit']
        }
    game = e.SingleGame(payload).create()
    new_game_id = game.created_game.id

    out = r.delete(url('/games/{}'.format(new_game_id))).json()
    print(out)




test_SingleGame()

