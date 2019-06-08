import json
import shutil

import pytest
from constant_sorrow.constants import NO_KEYRING_ATTACHED

from nucypher.characters.lawful import Alice
from nucypher.characters.lawful import Ursula
from nucypher.config.base import BaseConfiguration
from nucypher.config.characters import UrsulaConfiguration, AliceConfiguration, BobConfiguration
from nucypher.config.storages import ForgetfulNodeStorage
from nucypher.utilities.sandbox.constants import TEMPORARY_DOMAIN


def test_base_configuration():

    class Something(BaseConfiguration):
        _NAME = 'something'
        DEFAULT_CONFIG_ROOT = '/tmp'

        def __init__(self, item: str, *args, **kwargs):
            self.item = item
            super().__init__(*args, **kwargs)

        def static_payload(self) -> dict:
            payload = dict(item=self.item)
            return payload

    # Create something
    s = Something(item='llamas')

    # Dump to JSON file
    shutil.rmtree(Something.default_filepath(), ignore_errors=True)
    s.to_configuration_file(override=True)

    try:
        with open(s.filepath, 'r') as f:
            contents = f.read()
        assert contents == json.dumps(s.static_payload(), indent=4)

        # Restore from JSON file
        s2 = Something.from_configuration_file()
        assert s == s2
        assert s.item == 'llamas'

    finally:
        shutil.rmtree(s.filepath, ignore_errors=True)


@pytest.mark.parametrize("configuration,character", [(UrsulaConfiguration, Ursula),
                                                     (AliceConfiguration, Alice)])
def test_federated_development_configurations(configuration, character):

    config = configuration(dev_mode=True, federated_only=True)
    assert config.is_me is True
    assert config.dev_mode is True
    assert config.keyring == NO_KEYRING_ATTACHED
    assert config.provider_uri == configuration.DEFAULT_PROVIDER_URI

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
    assert configuration.TEMP_CONFIGURATION_DIR_PREFIX in thing_one.keyring_dir
    assert isinstance(thing_one.node_storage, ForgetfulNodeStorage)
    assert thing_one.node_storage._name == ":memory:"

    # All development characters are unique
    characters = [thing_one, thing_two]
    for _ in range(3):
        another_character = config()
        assert another_character not in characters
        characters.append(another_character)


@pytest.mark.parametrize('configuration_class', (UrsulaConfiguration,
                                                 AliceConfiguration,
                                                 BobConfiguration))
def test_create_standard_character_configuration(configuration_class):

    class TempConfiguration(configuration_class):
        DEFAULT_CONFIG_ROOT = '/tmp'

    character_config = TempConfiguration(checksum_address='0xdeadbeef')
    character_config.to_configuration_file(override=True)

    try:
        with open(character_config.filepath, 'r') as f:
            contents = f.read()
        assert contents == json.dumps(character_config.static_payload(), indent=4)

        # Restore from JSON file
        ursula_config2 = TempConfiguration.from_configuration_file()
        assert character_config == ursula_config2

    finally:
        shutil.rmtree(character_config.filepath, ignore_errors=True)

