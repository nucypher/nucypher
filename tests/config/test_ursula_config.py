import tempfile

from constant_sorrow.constants import NO_KEYRING_ATTACHED, CERTIFICATE_NOT_SAVED

from nucypher.characters.lawful import Ursula
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.storages import ForgetfulNodeStorage


def test_ursula_development_configuration(federated_only=True):
    config = UrsulaConfiguration(dev_mode=True, federated_only=federated_only)
    assert config.is_me is True
    assert config.dev_mode is True
    assert config.keyring == NO_KEYRING_ATTACHED
    assert config.provider_uri == UrsulaConfiguration.DEFAULT_PROVIDER_URI

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
    assert UrsulaConfiguration.TEMP_CONFIGURATION_DIR_PREFIX in ursula_one.keyring_dir
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
