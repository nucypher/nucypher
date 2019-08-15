import json
import os
import tempfile

import pytest
from constant_sorrow.constants import NO_KEYRING_ATTACHED, CERTIFICATE_NOT_SAVED, NO_BLOCKCHAIN_CONNECTION

from nucypher.characters.chaotic import Felix
from nucypher.characters.lawful import Alice, Bob
from nucypher.characters.lawful import Ursula
from nucypher.config.base import BaseConfiguration
from nucypher.config.characters import AliceConfiguration, BobConfiguration, FelixConfiguration
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.storages import ForgetfulNodeStorage
from nucypher.utilities.sandbox.constants import TEMPORARY_DOMAIN

# Main Cast
configurations = (AliceConfiguration, BobConfiguration, UrsulaConfiguration)
characters = (Alice, Bob, Ursula)

# Auxiliary Support
blockchain_only_configurations = (FelixConfiguration, )
blockchain_only_characters = (Felix, )

# Assemble
characters_and_configurations = list(zip(characters, configurations))
all_characters = tuple(characters + blockchain_only_characters)
all_configurations = tuple(configurations + blockchain_only_configurations)


@pytest.mark.parametrize("character,configuration", characters_and_configurations)
def test_federated_development_character_configurations(character, configuration):

    config = configuration(dev_mode=True, federated_only=True)
    assert config.is_me is True
    assert config.dev_mode is True
    assert config.keyring == NO_KEYRING_ATTACHED
    assert config.provider_uri == NO_BLOCKCHAIN_CONNECTION

    # Production
    thing_one = config()

    # Alternate way to produce a character with a direct call
    thing_two = config.produce()
    assert isinstance(thing_two, character)

    # Ensure we do in fact have a character here
    assert isinstance(thing_one, character)

    # Ethereum Address
    assert len(thing_one.checksum_address) == 42

    # Operating Mode
    assert thing_one.federated_only is True

    # Domains
    domains = thing_one.learning_domains
    assert domains == [TEMPORARY_DOMAIN]

    # Node Storage
    assert configuration.TEMP_CONFIGURATION_DIR_PREFIX in thing_one.keyring_root
    assert isinstance(thing_one.node_storage, ForgetfulNodeStorage)
    assert thing_one.node_storage._name == ":memory:"

    # All development characters are unique
    _characters = [thing_one, thing_two]
    for _ in range(3):
        another_character = config()
        assert another_character not in _characters
        _characters.append(another_character)


@pytest.mark.parametrize('configuration_class', all_configurations)
def test_default_character_configuration_preservation(configuration_class):

    configuration_class.DEFAULT_CONFIG_ROOT = '/tmp'
    fake_address = '0xdeadbeef'

    expected_filename = f'{configuration_class._NAME}.{configuration_class._CONFIG_FILE_EXTENSION}'
    generated_filename = configuration_class.generate_filename()
    assert generated_filename == expected_filename
    expected_filepath = os.path.join('/', 'tmp', generated_filename)

    if os.path.exists(expected_filepath):
        os.remove(expected_filepath)
    assert not os.path.exists(expected_filepath)

    character_config = configuration_class(checksum_address=fake_address)

    generated_filepath = character_config.generate_filepath()
    assert generated_filepath == expected_filepath

    written_filepath = character_config.to_configuration_file()
    assert written_filepath == expected_filepath
    assert os.path.exists(written_filepath)

    try:
        # Read
        with open(character_config.filepath, 'r') as f:
            contents = f.read()

        # Deserialize
        serialized_payload = json.dumps(character_config.static_payload(), indent=BaseConfiguration.INDENTATION)
        assert contents == serialized_payload

        # Restore from JSON file
        restored_configuration = configuration_class.from_configuration_file()
        assert character_config == restored_configuration

        # File still exists after reading
        assert os.path.exists(written_filepath)

    finally:
        if os.path.exists(expected_filepath):
            os.remove(expected_filepath)


def test_ursula_development_configuration(federated_only=True):
    config = UrsulaConfiguration(dev_mode=True, federated_only=federated_only)
    assert config.is_me is True
    assert config.dev_mode is True
    assert config.keyring == NO_KEYRING_ATTACHED

    # Produce an Ursula
    ursula_one = config()

    # Ensure we do in fact have an Ursula here
    assert isinstance(ursula_one, Ursula)
    assert len(ursula_one.checksum_address) == 42
    assert ursula_one.federated_only is federated_only

    # A Temporary Ursula
    port = ursula_one.rest_information()[0].port
    assert port == UrsulaConfiguration.DEFAULT_DEVELOPMENT_REST_PORT
    assert tempfile.gettempdir() in ursula_one.datastore.engine.url.database
    assert ursula_one.certificate_filepath is CERTIFICATE_NOT_SAVED
    assert UrsulaConfiguration.TEMP_CONFIGURATION_DIR_PREFIX in ursula_one.keyring_root
    assert isinstance(ursula_one.node_storage, ForgetfulNodeStorage)
    assert ursula_one.node_storage._name == ":memory:"

    # Alternate way to produce a character with a direct call
    ursula_two = config.produce()
    assert isinstance(ursula_two, Ursula)

    # All development Ursulas are unique
    ursulas = [ursula_one, ursula_two]
    for _ in range(3):
        ursula = config()
        assert ursula not in ursulas
        ursulas.append(ursula)
