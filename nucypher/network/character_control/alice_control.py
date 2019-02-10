from flask import Flask, request, Response
import maya

from nucypher.characters.lawful import Alice, Bob
from nucypher.crypto.powers import DecryptingPower, SigningPower


def make_alice_control(drone_alice: Alice):
    alice_control = Flask("alice-control")

    @alice_control.route("/create_policy", methods=['PUT'])
    def create_policy():
        """
        Character control endpoint for creating a policy and making
        arrangements with Ursulas.
        """
        # TODO: Needs input cleansing and validation
        # TODO: Provide more informative errors
        try:
            bob_pubkey = bytes.fromhex(request.args['bob_encrypting_key'])
            label = bytes.fromhex(request.args['label'])
            # TODO: Do we change this to something like "threshold"
            m, n = int(request.args['m']), int(request.args['n'])
            payment_details = request.args['payment']
            federated_only = True # const for now

            bob = Bob.from_public_keys({DecryptingPower: bob_pubkey,
                                        SigningPower: None},
                                       federated_only=True)
        except KeyError as e:
            return Response(str(e), status=500)

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
            bob_pubkey = bytes.fromhex(request.args['bob_encrypting_key'])
            label = bytes.fromhex(request.args['label'])
            # TODO: Do we change this to something like "threshold"
            m, n = int(request.args['m']), int(request.args['n'])
            expiration_time = maya.MayaDT.from_iso8601(
                                            request.args['expiration_time'])
            payment_details = request.args['payment']
            federated_only = True # const for now

            bob = Bob.from_public_keys({DecryptingPower: bob_pubkey,
                                        SigningPower: None},
                                       federated_only=True)
        except KeyError as e:
            return Response(str(e), status=500)

        new_policy = drone_alice.grant(bob, label, m=m, n=n,
                                       expiration=expiration_time)
        # TODO: Serialize the policy
        import pudb; pudb.set_trace()
        return Response(bytes(new_policy.treasure_map), status=200)

    return alice_control
