from nucypher.characters.control.interfaces import PUBLIC_INTERFACES


"""
Test that the various methods of compiling schema info yield identical
and compatible results
"""


def test_specified_interfaces(federated_alice):

    alice = federated_alice._interface_class(federated_alice)
    assert alice.schema_spec['grant']['properties']['bob_encrypting_key']['type'] == 'string'
    assert alice.schema_spec['grant']['properties']['bob_encrypting_key']['format'] == 'key'
    assert alice.schema_spec['grant']['properties']['expiration']['format'] == 'date-iso8601'

    bob = PUBLIC_INTERFACES['bob']()
    assert bob.schema_spec['retrieve']['properties']['label']['type'] == 'string'
    assert bob.schema_spec['retrieve']['properties']['message_kit']['type'] == 'string'
    assert bob.schema_spec['retrieve']['properties']['message_kit']['format'] == 'base64'

    enrico = PUBLIC_INTERFACES['enrico']()
    assert enrico.schema_spec['encrypt']['properties']['message']['type'] == 'string'
    assert enrico.schema_spec['encrypt']['properties']['message']['format'] == 'textfield'


def test_adhoc_interfaces():

    staker = PUBLIC_INTERFACES['staker']()
    assert staker.schema_spec['accounts']['properties']['staking_address']['type'] == 'string'
    assert staker.schema_spec['accounts']['properties']['staking_address']['format'] == 'checksum_address'

    assert 'winddown' in staker.schema_spec
    assert staker.schema_spec['winddown']['properties']['beneficiary_address']['type'] == 'string'
    assert staker.schema_spec['winddown']['properties']['beneficiary_address']['format'] == 'checksum_address'

    ursula = PUBLIC_INTERFACES['ursula']()
    assert ursula.schema_spec['config']['properties']['poa']['type'] == 'boolean'

    staker = PUBLIC_INTERFACES['alice']()
    assert 'debug' not in ursula.schema_spec['config']['properties']
