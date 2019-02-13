import datetime
import json
import maya

from base64 import b64encode, b64decode
from umbral.keys import UmbralPublicKey

from nucypher.characters.lawful import Enrico
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import DecryptingPower
from nucypher.policy.models import TreasureMap


def test_alice_character_control_create_policy(alice_control, federated_bob):
    bob_pubkey_enc = federated_bob.public_keys(DecryptingPower)

    request_data = {
        'bob_encrypting_key': bytes(bob_pubkey_enc).hex(),
        'label': b64encode(bytes(b'test')).decode(),
        'm': 2,
        'n': 3,

    }
    response = alice_control.put('/create_policy', data=json.dumps(request_data))
    assert response.status_code == 200
    assert response.data == b'Policy created!'

    # Send bad data to assert error returns
    response = alice_control.put('/create_policy', data='bad')
    assert response.status_code == 400

    del(request_data['bob_encrypting_key'])
    response = alice_control.put('/create_policy', data=json.dumps(request_data))


def test_alice_character_control_grant(alice_control, federated_bob):
    bob_pubkey_enc = federated_bob.public_keys(DecryptingPower)

    request_data = {
        'bob_encrypting_key': bytes(bob_pubkey_enc).hex(),
        'label': b64encode(bytes(b'test')).decode(),
        'm': 2,
        'n': 3,
        'expiration_time': (maya.now() + datetime.timedelta(days=3)).iso8601(),
    }
    response = alice_control.put('/grant', data=json.dumps(request_data))
    assert response.status_code == 200

    response_data = json.loads(response.data)
    assert 'treasure_map' in response_data['result']
    assert 'policy_encrypting_pubkey' in response_data['result']
    assert 'alice_signing_pubkey' in response_data['result']
    assert 'label' in response_data['result']

    map_bytes = b64decode(response_data['result']['treasure_map'])
    encrypted_map = TreasureMap.from_bytes(map_bytes)
    assert encrypted_map._hrac is not None

    # Send bad data to assert error returns
    response = alice_control.put('/grant', data='bad')
    assert response.status_code == 400

    del(request_data['bob_encrypting_key'])
    response = alice_control.put('/grant', data=json.dumps(request_data))


def test_bob_character_control_join_policy(bob_control, enacted_federated_policy):
    request_data = {
        'label': b64encode(enacted_federated_policy.label).decode(),
        'alice_signing_pubkey': bytes(enacted_federated_policy.alice.stamp).hex(),
    }

    response = bob_control.post('/join_policy', data=json.dumps(request_data))
    assert response.data == b'Policy joined!'
    assert response.status_code == 200

    # Send bad data to assert error returns
    response = bob_control.post('/join_policy', data='bad')
    assert response.status_code == 400

    del(request_data['alice_signing_pubkey'])
    response = bob_control.put('/join_policy', data=json.dumps(request_data))


def test_bob_character_control_retrieve(bob_control, enacted_federated_policy, capsule_side_channel):
    message_kit, data_source = capsule_side_channel

    request_data = {
        'label': b64encode(enacted_federated_policy.label).decode(),
        'policy_encrypting_pubkey': bytes(enacted_federated_policy.public_key).hex(),
        'alice_signing_pubkey': bytes(enacted_federated_policy.alice.stamp).hex(),
        'message_kit': b64encode(message_kit.to_bytes()).decode(),
        'datasource_signing_pubkey': bytes(data_source.stamp).hex(),
    }

    response = bob_control.post('/retrieve', data=json.dumps(request_data))
    assert response.status_code == 200

    response_data = json.loads(response.data)
    assert 'plaintext' in response_data['result']

    for plaintext in response_data['result']['plaintext']:
        assert b64decode(plaintext) == b'Welcome to the flippering.'

    # Send bad data to assert error returns
    response = bob_control.post('/retrieve', data='bad')
    assert response.status_code == 400

    del(request_data['alice_signing_pubkey'])
    response = bob_control.put('/retrieve', data=json.dumps(request_data))


def test_enrico_character_control_encrypt_message(enrico_control):

    request_data = {
        'message': b64encode(b"The admiration I had for your work has completely evaporated!").decode(),
    }

    response = enrico_control.post('/encrypt_message', data=json.dumps(request_data))
    assert response.status_code == 200

    response_data = json.loads(response.data)
    assert 'message_kit' in response_data['result']
    assert 'signature' in response_data['result']

    # Check that it serializes correctly.
    message_kit = UmbralMessageKit.from_bytes(
                            b64decode(response_data['result']['message_kit']))

    # Send bad data to assert error return
    response = enrico_control.post('/encrypt_message', data='bad')
    assert response.status_code == 400

    del(request_data['message'])
    response = enrico_control.post('/encrypt_message', data=request_data)
    assert response.status_code == 400


def test_character_control_lifecycle(alice_control, bob_control,
                                     enrico_control_from_alice,
                                     federated_alice, federated_bob):

    # Create a policy via Alice control
    alice_request_data = {
        'bob_encrypting_key': bytes(federated_bob.public_keys(DecryptingPower)).hex(),
        'label': b64encode(b'test').decode(),
        #'bob_signing_key': bytes(federated_bob.stamp).hex(),
        'm': 2, 'n': 3,
        'expiration_time': (maya.now() + datetime.timedelta(days=3)).iso8601(),
    }

    response = alice_control.put('/grant', data=json.dumps(alice_request_data))
    assert response.status_code == 200

    alice_response_data = json.loads(response.data)
    assert 'treasure_map' in alice_response_data['result']
    assert 'policy_encrypting_pubkey' in alice_response_data['result']
    assert 'alice_signing_pubkey' in alice_response_data['result']
    assert 'label' in alice_response_data['result']

    # This is sidechannel policy metadata. It should be given to Bob by the
    # application developer at some point.
    policy_pubkey_enc_hex = alice_response_data['result']['policy_encrypting_pubkey']
    alice_pubkey_sig_hex = alice_response_data['result']['alice_signing_pubkey']
    label = b64decode(alice_response_data['result']['label'])

    # Encrypt some data via Enrico control
    # Alice will also be Enrico via Enrico.from_alice
    # (see enrico_control_from_alice fixture)
    enrico_request_data = {
        'message': b64encode(b"I'm bereaved, not a sap!").decode(),
    }

    response = enrico_control_from_alice.post('/encrypt_message', data=json.dumps(enrico_request_data))
    assert response.status_code == 200

    enrico_response_data = json.loads(response.data)
    assert 'message_kit' in enrico_response_data['result']
    assert 'signature' in enrico_response_data['result']

    kit_bytes = b64decode(enrico_response_data['result']['message_kit'])
    bob_message_kit = UmbralMessageKit.from_bytes(kit_bytes)

    # Retrieve data via Bob control
    bob_request_data = {
        'label': b64encode(label).decode(),
        'policy_encrypting_pubkey': policy_pubkey_enc_hex,
        'alice_signing_pubkey': alice_pubkey_sig_hex,
        'message_kit': b64encode(bob_message_kit.to_bytes()).decode(),
    }

    response = bob_control.post('/retrieve', data=json.dumps(bob_request_data))
    assert response.status_code == 200

    bob_response_data = json.loads(response.data)
    assert 'plaintext' in bob_response_data['result']

    for plaintext in bob_response_data['result']['plaintext']:
        plaintext_bytes = b64decode(plaintext)
        assert plaintext_bytes == b"I'm bereaved, not a sap!"
