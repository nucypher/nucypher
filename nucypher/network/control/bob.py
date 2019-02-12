import json

from base64 import b64encode, b64decode
from flask import Flask, request, Response

from json.decoder import JSONDecodeError
from umbral.keys import UmbralPublicKey

from nucypher.characters.lawful import Bob, Ursula
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.data_sources import DataSource


def make_bob_control(drone_bob: Bob, teacher_node: Ursula):
    bob_control = Flask('bob-control')

    teacher_node.verify_node(drone_bob.network_middleware)
    drone_bob.remember_node(teacher_node)
    drone_bob.start_learning_loop(now=True)

    @bob_control.route('/join_policy', methods=['POST'])
    def join_policy():
        """
        Character control endpoint for joining a policy on the network.

        This is an unfinished endpoint. You're probably looking for retrieve.
        """
        try:
            request_data = json.loads(request.data)

            label = b64decode(request_data['label'])
            alice_pubkey_sig = bytes.fromhex(request_data['alice_signing_pubkey'])
        except (KeyError, JSONDecodeError) as e:
            return Response(e, status=400)

        drone_bob.join_policy(label=label, alice_pubkey_sig=alice_pubkey_sig)

        return Response('Policy joined!', status=200)


    @bob_control.route('/retrieve', methods=['POST'])
    def retrieve():
        """
        Character control endpoint for re-encrypting and decrypting policy
        data.
        """
        try:
            request_data = json.loads(request.data)

            label = b64decode(request_data['label'])
            policy_pubkey_enc = bytes.fromhex(request_data['policy_encrypting_pubkey'])
            alice_pubkey_sig = bytes.fromhex(request_data['alice_signing_pubkey'])
            datasource_pubkey_sig = bytes.fromhex(request_data['datasource_signing_pubkey'])
            message_kit = b64decode(request_data['message_kit'])
        except (KeyError, JSONDecodeError) as e:
            return Response(e, status=400)

        policy_pubkey_enc = UmbralPublicKey.from_bytes(policy_pubkey_enc)
        alice_pubkey_sig = UmbralPublicKey.from_bytes(alice_pubkey_sig)
        message_kit = UmbralMessageKit.from_bytes(message_kit)

        data_source = DataSource.from_public_keys(policy_pubkey_enc,
                                                  datasource_pubkey_sig,
                                                  label=label)
        drone_bob.join_policy(label=label, alice_pubkey_sig=alice_pubkey_sig)
        plaintexts = drone_bob.retrieve(message_kit=message_kit,
                                        data_source=data_source,
                                        alice_verifying_key=alice_pubkey_sig)

        plaintexts = [b64encode(plaintext).decode() for plaintext in plaintexts]
        response_data = {
            'result': {
                'plaintext': plaintexts,
            }
        }

        return Response(json.dumps(response_data), status=200)

    return bob_control
