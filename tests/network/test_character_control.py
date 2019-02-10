import datetime
import maya

from nucypher.crypto.powers import DecryptingPower
from nucypher.policy.models import TreasureMap


def test_alice_character_control_create_policy(alice_control, federated_bob):
    bob_pubkey_enc = federated_bob.public_keys(DecryptingPower)

    request_data = {
        'bob_encrypting_key': bytes(bob_pubkey_enc).hex(),
        'label': bytes(b'test').hex(),
        'm': 2,
        'n': 3,
        'payment': b'',

    }
    response = alice_control.put('/create_policy', query_string=request_data)
    assert response.status_code == 200
    assert response.data == b'Policy created!'


def test_alice_character_control_grant(alice_control, federated_bob):
    bob_pubkey_enc = federated_bob.public_keys(DecryptingPower)

    request_data = {
        'bob_encrypting_key': bytes(bob_pubkey_enc).hex(),
        'label': bytes(b'test').hex(),
        'm': 2,
        'n': 3,
        'expiration_time': (maya.now() + datetime.timedelta(days=3)).iso8601(),
        'payment': {'tx': 'blah'},
    }
    response = alice_control.put('/grant', query_string=request_data)
    assert response.status_code == 200

    encrypted_map = TreasureMap.from_bytes(response.data)
    assert encrypted_map._hrac != None
