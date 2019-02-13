import json

from base64 import b64encode, b64decode
from flask import Flask, request, Response

from json.decoder import JSONDecodeError
from umbral.keys import UmbralPublicKey

from nucypher.characters.lawful import Bob, Ursula
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.characters.lawful import Enrico
