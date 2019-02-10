from nucypher.crypto.powers import DecryptingPower
from nucypher.network.character_control.alice_control import make_alice_control


def test_alice_character_control_create_policy(alice_control, federated_bob):
    bob_pubkey_enc = federated_bob.public_keys(DecryptingPower)

    content = {
        'bob_encrypting_key': bytes(bob_pubkey_enc).hex(),
        'label': bytes(b'test').hex(),
        'm': 2,
        'n': 3,
        'payment': {'tx': 'blah'},

    }
    response = alice_control.put('/create_policy', query_string=content)
    assert response.data == b'Policy created!'
