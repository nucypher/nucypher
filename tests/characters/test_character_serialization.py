import pytest
from nucypher.characters.lawful import Ursula


def test_serialize_ursula(federated_ursulas):
    ursula = federated_ursulas.pop()
    ursula_as_bytes = bytes(ursula)
    ursula_object = Ursula.from_bytes(ursula_as_bytes, federated_only=True)
    assert ursula == ursula_object
