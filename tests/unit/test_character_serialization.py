from nucypher.characters.lawful import Ursula


def test_serialize_ursula(blockchain_ursulas):
    ursula = blockchain_ursulas[5]
    ursula_as_bytes = bytes(ursula.metadata())
    ursula_object = Ursula.from_metadata_bytes(ursula_as_bytes)
    assert ursula == ursula_object
    ursula.stop()
