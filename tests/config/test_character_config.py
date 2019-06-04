import tempfile

import pytest
from constant_sorrow.constants import NO_KEYRING_ATTACHED, CERTIFICATE_NOT_SAVED
from nucypher.characters.lawful import Ursula, Alice
from nucypher.config.characters import UrsulaConfiguration, AliceConfiguration

from nucypher.config.storages import ForgetfulNodeStorage
from nucypher.utilities.sandbox.constants import TEMPORARY_DOMAIN


@pytest.mark.parametrize("configuration,character", [(UrsulaConfiguration, Ursula), (AliceConfiguration, Alice)])
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
    assert domains == {TEMPORARY_DOMAIN}

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


def test_federated_ursula_development_configuration():

    # Configure & Produce Ursula
    ursula_config = UrsulaConfiguration(dev_mode=True, federated_only=True)
    ursula = ursula_config.produce()

    # Network Port
    port = ursula.rest_information()[0].port
    assert port == UrsulaConfiguration.DEFAULT_DEVELOPMENT_REST_PORT

    # Database
    assert tempfile.gettempdir() in ursula.datastore.engine.url.database

    # TLS Certificate
    assert ursula.certificate_filepath is CERTIFICATE_NOT_SAVED
