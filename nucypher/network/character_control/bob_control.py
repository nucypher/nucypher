from flask import Flask, request, Response

def make_bob_control(drone_bob: 'Bob'):
    bob_control = Flask('bob-control')

    return bob_control
