import json
from pathlib import Path

import pytest
from constant_sorrow.constants import NO_KEYSTORE_ATTACHED
from eth_utils import is_checksum_address
from nucypher_core.umbral import SecretKey

from nucypher.characters.lawful import Alice, Bob, Ursula
from nucypher.config.characters import (
    AliceConfiguration,
    BobConfiguration,
    UrsulaConfiguration,
)
from nucypher.config.constants import TEMPORARY_DOMAIN_NAME
from nucypher.crypto.keystore import Keystore
from tests.constants import (
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_ETH_PROVIDER_URI,
    MOCK_IP_ADDRESS,
)
from tests.utils.blockchain import ReservedTestAccountManager

# Main Cast
configurations = (AliceConfiguration, BobConfiguration, UrsulaConfiguration)
characters = (Alice, Bob, Ursula)

# Assemble
characters_and_configurations = list(zip(characters, configurations))
all_characters = tuple(
    characters,
)
all_configurations = tuple(
    configurations,
)


@pytest.mark.usefixtures(
    "mock_registry_sources",
    "monkeypatch_get_staking_provider_from_operator"
)
@pytest.mark.parametrize("character,configuration", characters_and_configurations)
def test_development_character_configurations(
    character, configuration
):
    params = dict(
        dev_mode=True,
        lonely=True,
        domain=TEMPORARY_DOMAIN_NAME,
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
        polygon_endpoint=MOCK_ETH_PROVIDER_URI,
    )
    config = configuration(**params)

    assert config.is_peer is False
    assert config.dev_mode is True
    assert config.keystore == NO_KEYSTORE_ATTACHED
    assert config.wallet is not None

    # Production
    thing_one = config()

    # Alternate way to produce a character with a direct call
    thing_two = config.produce()
    assert isinstance(thing_two, character)

    # Ensure we do in fact have a character here
    assert isinstance(thing_one, character)

    # Ethereum Address
    assert is_checksum_address(thing_one.wallet.address)
    assert len(thing_one.wallet.address) == 42

    # Domain
    assert TEMPORARY_DOMAIN_NAME == str(thing_one.domain)

    # All development characters are unique
    _characters = [thing_one, thing_two]
    for _ in range(3):
        another_character = config()
        assert another_character not in _characters
        _characters.append(another_character)

    if character is Alice:
        for alice in _characters:
            alice.disenchant()


@pytest.mark.parametrize("configuration_class", all_configurations)
def test_default_character_configuration_preservation(
    configuration_class,
    testerchain,
    tmpdir,
    test_registry,
):
    configuration_class.DEFAULT_CONFIG_ROOT = Path("/tmp")
    domain = TEMPORARY_DOMAIN_NAME

    expected_filename = (
        f"{configuration_class.NAME}.{configuration_class._CONFIG_FILE_EXTENSION}"
    )
    generated_filename = configuration_class.generate_filename()
    assert generated_filename == expected_filename
    expected_filepath = Path("/", "tmp", generated_filename)

    if expected_filepath.exists():
        expected_filepath.unlink()
    assert not expected_filepath.exists()

    if configuration_class == UrsulaConfiguration:
        # special case for host & dev mode use keystore
        keystore = Keystore.from_mnemonic(
            phrase=ReservedTestAccountManager._MNEMONIC,
            password=INSECURE_DEVELOPMENT_PASSWORD,
            keystore_dir=tmpdir
        )
        keystore.signing_public_key = SecretKey.random().public_key()
        character_config = configuration_class(
            eth_endpoint=MOCK_ETH_PROVIDER_URI,
            domain=domain,
            host=MOCK_IP_ADDRESS,
            polygon_endpoint=MOCK_ETH_PROVIDER_URI,
            keystore=keystore,
        )

    else:
        character_config = configuration_class(
            eth_endpoint=MOCK_ETH_PROVIDER_URI,
            domain=domain,
        )

    generated_filepath = character_config.generate_filepath()
    assert generated_filepath == expected_filepath

    written_filepath = character_config.to_configuration_file()
    assert written_filepath == expected_filepath
    assert written_filepath.exists()

    try:
        # Read
        with open(character_config.filepath, "r") as f:
            _contents = json.loads(
                f.read()
            )  # ensure this can be read and is valid JSON

        # Restore from JSON file
        restored_configuration = configuration_class.from_configuration_file()
        assert json.loads(character_config.serialize()) == json.loads(
            restored_configuration.serialize()
        )

        # File still exists after reading
        assert written_filepath.exists()

    finally:
        if expected_filepath.exists():
            expected_filepath.unlink()


def test_ursula_development_configuration(testerchain):
    config = UrsulaConfiguration(
        dev_mode=True,
        domain=TEMPORARY_DOMAIN_NAME,
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
        polygon_endpoint=MOCK_ETH_PROVIDER_URI,
    )
    assert config.is_peer is False
    assert config.dev_mode is True
    assert config.keystore == NO_KEYSTORE_ATTACHED

    # Produce an Ursula
    ursula_one = config()

    # Ensure we do in fact have an Ursula here
    assert isinstance(ursula_one, Ursula)
    assert len(ursula_one.wallet.address) == 42

    # A Temporary Ursula
    port = ursula_one.rest_information()[0].port
    assert port == UrsulaConfiguration.DEFAULT_DEVELOPMENT_REST_PORT

    # Alternate way to produce a character with a direct call
    ursula_two = config.produce()
    assert isinstance(ursula_two, Ursula)

    # All development Ursulas are unique
    ursulas = [ursula_one, ursula_two]
    for _ in range(3):
        ursula = config()
        assert ursula not in ursulas
        ursulas.append(ursula)

    for ursula in ursulas:
        ursula.stop()
