from nucypher.characters.control.interfaces import AliceInterface, BobInterface, EnricoInterface


def test_AliceInterface(federated_alice):

    interface = federated_alice._interface_class(federated_alice)

    # test custom field attrs
    assert interface.schema_spec['grant']['properties']['bob_encrypting_key']['type'] == 'string'
    assert interface.schema_spec['grant']['properties']['bob_encrypting_key']['format'] == 'key'
    assert interface.schema_spec['grant']['properties']['expiration']['format'] == 'date-iso8601'
