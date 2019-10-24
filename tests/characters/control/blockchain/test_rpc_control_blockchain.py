import pytest

from base64 import b64encode
from nucypher.characters.control.specifications import AliceSpecification, BobSpecification, EnricoSpecification
from nucypher.policy.collections import TreasureMap
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.network.nodes import Learner

alice_specification = AliceSpecification()
bob_specification = BobSpecification()
enrico_specification = EnricoSpecification()


def validate_json_rpc_response_data(response, method_name, specification):
    _input_fields, _optional_fields, required_output_fileds = specification.get_specifications(interface_name=method_name)
    assert 'jsonrpc' in response.data
    for output_field in required_output_fileds:
        assert output_field in response.content
    return True


def test_alice_rpc_character_control_create_policy(alice_rpc_test_client, create_policy_control_request):
    alice_rpc_test_client.__class__.MESSAGE_ID = 0
    method_name, params = create_policy_control_request
    request_data = {'method': method_name, 'params': params}
    rpc_response = alice_rpc_test_client.send(request=request_data)
    assert rpc_response.success is True
    assert rpc_response.id == 1

    _input_fields, _optional_fields, required_output_fileds = alice_specification.get_specifications(interface_name=method_name)

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
        request_data = {'method': method_name, 'params': params}
        bulk_request.append(request_data)

    rpc_responses = alice_rpc_test_client.send(request=bulk_request)
    for response_id, rpc_response in enumerate(rpc_responses, start=3):
        assert rpc_response.success is True
        assert rpc_response.id == response_id


def test_alice_rpc_character_control_derive_policy_encrypting_key(alice_rpc_test_client):
    method_name = 'derive_policy_encrypting_key'
    request_data = {'method': method_name, 'params': {'label': 'test'}}
    response = alice_rpc_test_client.send(request_data)
    assert response.success is True
    assert validate_json_rpc_response_data(response=response,
                                           method_name=method_name,
                                           specification=alice_specification)


def test_alice_rpc_character_control_grant(alice_rpc_test_client, grant_control_request):
    method_name, params = grant_control_request
    request_data = {'method': method_name, 'params': params}
    response = alice_rpc_test_client.send(request_data)
    assert validate_json_rpc_response_data(response=response,
                                           method_name=method_name,
                                           specification=alice_specification)


def test_bob_rpc_character_control_join_policy(bob_rpc_controller, join_control_request, enacted_federated_policy):

    # Simulate passing in a teacher-uri
    enacted_federated_policy.bob.remember_node(list(enacted_federated_policy.accepted_ursulas)[0])

    method_name, params = join_control_request
    request_data = {'method': method_name, 'params': params}
    response = bob_rpc_controller.send(request_data)
    assert validate_json_rpc_response_data(response=response,
                                           method_name=method_name,
                                           specification=bob_specification)


def test_enrico_rpc_character_control_encrypt_message(enrico_rpc_controller_test_client, encrypt_control_request):
    method_name, params = encrypt_control_request
    request_data = {'method': method_name, 'params': params}
    response = enrico_rpc_controller_test_client.send(request_data)
    assert validate_json_rpc_response_data(response=response,
                                           method_name=method_name,
                                           specification=enrico_specification)


def test_bob_rpc_character_control_retrieve(
        bob_rpc_controller, make_retrieve_control_request,
        blockchain_bob, blockchain_alice,
        capsule_side_channel_blockchain, enacted_blockchain_policy
        ):
    request_data = make_retrieve_control_request()
    response = bob_rpc_controller.send(request_data)
    assert validate_json_rpc_response_data(response=response,
                                           method_name=request_data['method'],
                                           specification=bob_specification)
    assert response.data['result']['cleartexts'][0] == 'Welcome to flippering number 2.'

    request_data = make_retrieve_control_request()
    tmap = b64encode(bytes(enacted_blockchain_policy.treasure_map)).decode()
    request_data['params']['treasure_map'] = tmap
    response = bob_rpc_controller.send(request_data)
    assert response.data['result']['cleartexts'][0] == 'Welcome to flippering number 3.'

    request_data = make_retrieve_control_request()
    wrong_tmap = TreasureMap(
            m=1,
            destinations={'0x0000000000000000000000000000000000000000': b'\x00' * 32})
    wrong_tmap.prepare_for_publication(
            blockchain_bob.public_keys(DecryptingPower),
            blockchain_bob.public_keys(SigningPower),
            blockchain_alice.stamp,
            b'Wrong!')
    wrong_tmap = b64encode(bytes(wrong_tmap)).decode()
    request_data['params']['treasure_map'] = wrong_tmap
    with pytest.raises(Learner.NotEnoughTeachers):
        bob_rpc_controller.send(request_data)
