import datetime
import json
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


def test_bob_character_control_join_policy(bob_control, enacted_federated_policy):
    request_data = {
        'label': enacted_federated_policy.label.hex(),
        'alice_signing_pubkey': bytes(enacted_federated_policy.alice.stamp).hex(),
    }

    response = bob_control.post('/join_policy', query_string=request_data)
    assert response.data == b'Policy joined!'
    assert response.status_code == 200


def test_bob_character_control_retrieve(bob_control, enacted_federated_policy, capsule_side_channel):
    message_kit, data_source = capsule_side_channel
    request_data = {
        'label': enacted_federated_policy.label.hex(),
        'policy_encrypting_pubkey': bytes(enacted_federated_policy.public_key).hex(),
        'alice_signing_pubkey': bytes(enacted_federated_policy.alice.stamp).hex(),
        'message_kit': message_kit.to_bytes().hex(),
        'datasource_signing_pubkey': bytes(data_source.stamp).hex(),
    }

    response = bob_control.post('/retrieve', query_string=request_data)

    plaintext = json.loads(response.data)
    assert response.status_code == 200
    assert bytes.fromhex(plaintext[0]) == b'Welcome to the flippering.'
