# A very simple Flask Hello World app for you to get started with...

from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello from Flask!'


@app.route('/games', methods=['GET'])
def games():
    out = [{'game1':'win'},{'game2':'lose'}]
    return jsonify(out)


