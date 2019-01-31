import elo_ball_app as e
import config
import requests as r
import datetime
import pytest

def url(endpoint):
    return config.base_url + endpoint

@pytest.fixture
def game():
    print('setup')
    yield {'ans':3}
    print('teardown')


def test_my_fix(game):
    assert 3 == game['ans']



# Call root - check its standing
def test_GET_root():
    resp = r.get(url('/'))
    assert resp.text == 'Howdy from Flask staging'

# Create game
def test_POST_games():
    current_timestamp = datetime.datetime.now().isoformat()
    payload = {
        'losers':['testgame'],
        'winners':['suckit'],
        'timestamp': current_timestamp
        }

    resp = r.post(url('/games'), json=payload)

    found_game = False
    for game in resp.json():
        if current_timestamp == game['timestamp']:
            found_game = True
    assert found_game


# Get all games

def test_GET_games():
    resp = r.get(url('/games'))
    assert resp.status_code == 200


# Delete game
def test_DELETE_games():
    # Create game
    payload = {
        'losers':['testgame'],
        'winners':['suckit']
        }
    game = e.SingleGame(payload).create()
    # Get ID
    new_game_id = game.created_game.id
    # Delete ID
    resp = r.delete(url('/games/{}'.format(new_game_id)))
    assert resp.status_code == 200
    # Game not in returned list
    game_not_found = True
    for game in resp.json():
        if game['id'] == new_game_id:
            game_not_found = False
    assert game_not_found

# Get list of players
def test_GET_players():
    resp = r.get(url('/players'))
    assert resp.status_code == 200
    expected_keys = set(['id','record', 'elo'])
    first_player_keys = set(resp.json()[0].keys())
    assert first_player_keys == expected_keys




