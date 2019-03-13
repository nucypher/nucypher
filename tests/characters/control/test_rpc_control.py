import random
from base64 import b64encode

import pytest

from nucypher.characters.control.specifications import AliceSpecification
from nucypher.crypto.powers import DecryptingPower
from nucypher.utilities.policy import generate_random_label


def test_alice_character_control_create_policy(alice_rpc_test_client, federated_bob):
    bob_pubkey_enc = federated_bob.public_keys(DecryptingPower)

    method_name = 'create_policy'

    params = {
        'bob_encrypting_key': bytes(bob_pubkey_enc).hex(),
        'bob_verifying_key': bytes(federated_bob.stamp).hex(),
        'label': b64encode(bytes(b'test')).decode(),
        'm': 2,
        'n': 3,
    }

    request_data = {'method': method_name, 'params': params}
    rpc_response = alice_rpc_test_client.send(request=request_data)
    assert rpc_response.success is True
    assert rpc_response.id == 1

    alice_specification = AliceSpecification()
    _input_fields, required_output_fileds = alice_specification.get_specifications(interface_name=method_name)

    assert 'jsonrpc' in rpc_response.data
    for output_field in required_output_fileds:
        assert output_field in rpc_response.content

    try:
        bytes.fromhex(rpc_response.content['policy_encrypting_key'])
    except (KeyError, ValueError):
        pytest.fail("Invalid Policy Encrypting Key")

    # Confirm the same message send works again, with a unique ID
    request_data = {'method': method_name, 'params': params}
    rpc_response = alice_rpc_test_client.send(request=request_data)
    assert rpc_response.success is True
    assert rpc_response.id == 2

    # Send bad data to assert error returns (Request #3)
    alice_rpc_test_client.crash_on_error = False
    response = alice_rpc_test_client.send(request={'bogus': 'input'}, malformed=True)
    assert response.error_code == -32600

    # Send a bulk create policy request
    bulk_request = list()
    for i in range(50):
        random_label = generate_random_label()
        m, n = random.choice(((1, 1), (2, 3), (3, 4)))
        params = {
            'bob_encrypting_key': bytes(bob_pubkey_enc).hex(),
            'bob_verifying_key': bytes(federated_bob.stamp).hex(),
            'label': b64encode(bytes(random_label)).decode(),
            'm': m,
            'n': n,
        }

        request_data = {'method': method_name, 'params': params}
        bulk_request.append(request_data)

    rpc_responses = alice_rpc_test_client.send(request=bulk_request)

    for response_id, rpc_response in enumerate(rpc_responses, start=3):
        assert rpc_response.success is True
        assert rpc_response.id == response_id


def test_alice_character_control_derive_policy_encrypting_key(alice_rpc_test_client):
    method_name = 'derive_policy_encrypting_key'
    label = 'test'
    request_data = {'method': method_name, 'params': {'label': label}}
    response = alice_rpc_test_client.send(request_data)
    assert response.success is True

    alice_specification = AliceSpecification()
    _input_fields, required_output_fileds = alice_specification.get_specifications(interface_name=method_name)

    assert 'jsonrpc' in response.data
    for output_field in required_output_fileds:
        assert output_field in response.content
