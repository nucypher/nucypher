import json
import maya

from base64 import b64encode, b64decode
from flask import Flask, request, Response
from json.decoder import JSONDecodeError

from nucypher.characters.lawful import Alice, Bob, Ursula
from nucypher.crypto.powers import DecryptingPower, SigningPower


def make_alice_control(drone_alice: Alice, teacher_node: Ursula):
    alice_control = Flask("alice-control")

    teacher_node.verify_node(drone_alice.network_middleware)
    drone_alice.remember_node(teacher_node)
    drone_alice.start_learning_loop(now=True)

    @alice_control.route("/create_policy", methods=['PUT'])
    def create_policy():
        """
        Character control endpoint for creating a policy and making
        arrangements with Ursulas.

        This is an unfinished API endpoint. You are probably looking for grant.
        """
        # TODO: Needs input cleansing and validation
        # TODO: Provide more informative errors
        try:
            request_data = json.loads(request.data)

            bob_pubkey = bytes.fromhex(request_data['bob_encrypting_key'])
            label = b64decode(request_data['label'])
            # TODO: Do we change this to something like "threshold"
            m, n = request_data['m'], request_data['n']
            federated_only = True  # const for now

            bob = Bob.from_public_keys({DecryptingPower: bob_pubkey,
                                        SigningPower: None},
                                       federated_only=True)
        except (KeyError, JSONDecodeError) as e:
            return Response(str(e), status=400)

        new_policy = drone_alice.create_policy(bob, label, m, n,
                                               federated=federated_only)
        # TODO: Serialize the policy
        return Response('Policy created!', status=200)

    @alice_control.route("/grant", methods=['PUT'])
    def grant():
        """
        Character control endpoint for policy granting.
        """
        # TODO: Needs input cleansing and validation
        # TODO: Provide more informative errors
        try:
            request_data = json.loads(request.data)

            bob_pubkey = bytes.fromhex(request_data['bob_encrypting_key'])
            label = b64decode(request_data['label'])
            # TODO: Do we change this to something like "threshold"
            m, n = request_data['m'], request_data['n']
            expiration_time = maya.MayaDT.from_iso8601(
                                            request_data['expiration_time'])
            federated_only = True  # const for now

            bob = Bob.from_public_keys({DecryptingPower: bob_pubkey,
                                        SigningPower: None},
                                       federated_only=True)
        except (KeyError, JSONDecodeError) as e:
            return Response(str(e), status=400)

        new_policy = drone_alice.grant(bob, label, m=m, n=n,
                                       expiration=expiration_time)
        # TODO: Serialize the policy
        response_data = {
            'result': {
                'treasure_map': b64encode(bytes(new_policy.treasure_map)).decode(),
            }
        }

        return Response(json.dumps(response_data), status=200)

    return alice_control
