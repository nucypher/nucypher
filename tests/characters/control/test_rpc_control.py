import pytest

from nucypher.characters.control.specifications import AliceSpecification, BobSpecification, EnricoSpecification

alice_specification = AliceSpecification()
bob_specification = BobSpecification()
enrico_specification = EnricoSpecification()


def validate_json_rpc_response_data(response, method_name, specification):
    _input_fields, required_output_fileds = specification.get_specifications(interface_name=method_name)
    assert 'jsonrpc' in response.data
    for output_field in required_output_fileds:
        assert output_field in response.content
    return True


def test_alice_rpc_character_control_create_policy(alice_rpc_test_client, create_policy_control_request):
    method_name, params = create_policy_control_request
    request_data = {'method': method_name, 'params': params}
    rpc_response = alice_rpc_test_client.send(request=request_data)
    assert rpc_response.success is True
    assert rpc_response.id == 1

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


def test_bob_rpc_character_control_retrieve(bob_rpc_controller, retrieve_control_request):
    method_name, params = retrieve_control_request
    request_data = {'method': method_name, 'params': params}
    response = bob_rpc_controller.send(request_data)
    assert validate_json_rpc_response_data(response=response,
                                           method_name=method_name,
                                           specification=bob_specification)
