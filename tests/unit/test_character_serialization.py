from nucypher.characters.lawful import Ursula


def test_serialize_ursula(light_ursula):
    ursula_as_bytes = bytes(light_ursula.metadata())
    ursula_object = Ursula.from_metadata_bytes(ursula_as_bytes)
    assert light_ursula == ursula_object
    light_ursula.stop()
