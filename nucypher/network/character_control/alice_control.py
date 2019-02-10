from flask import Flask

from nucypher.characters.lawful import Alice


def make_alice_control(drone_alice: Alice):
    alice_control = Flask("alice-control")

    @alice_control.route("/grant", methods=['POST'])
    def grant():
        """
        Character control endpoint for policy granting.
        """
        pass

    return alice_control
