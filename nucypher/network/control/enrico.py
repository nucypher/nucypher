import json

from base64 import b64encode, b64decode
from flask import Flask, request, Response
from json.decoder import JSONDecodeError

from nucypher.data_sources import DataSource


def make_enrico_control(drone_enrico: DataSource):
    enrico_control = Flask("enrico-control")

    @enrico_control.route('/encrypt_message', methods=['POST'])
    def encrypt_message():
        """
        Character control endpoint for encrypting data for a policy and
        receiving the messagekit (and signature) to give to Bob.
        """
        try:
            request_data = json.loads(request.data)

            message = b64decode(request_data['message'])
        except (KeyError, JSONDecodeError) as e:
            return Response(str(e), status=400)

        message_kit, signature = drone_enrico.encrypt_message(message)

        response_data = {
            'result': {
                'message_kit': b64encode(message_kit.to_bytes()).decode(),
                'signature': b64encode(bytes(signature)).decode(),
            }
        }

        return Response(json.dumps(response_data), status=200)

    return enrico_control
