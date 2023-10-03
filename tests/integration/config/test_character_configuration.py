import json
from pathlib import Path

import pytest
from constant_sorrow.constants import CERTIFICATE_NOT_SAVED, NO_KEYSTORE_ATTACHED
from nucypher_core.umbral import SecretKey

from nucypher.characters.lawful import Alice, Bob, Ursula
from nucypher.cli.actions.configure import destroy_configuration
from nucypher.cli.literature import SUCCESSFUL_DESTRUCTION
from nucypher.config.base import CharacterConfiguration
from nucypher.config.characters import (
    AliceConfiguration,
    BobConfiguration,
    UrsulaConfiguration,
)
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.config.storages import ForgetfulNodeStorage
from nucypher.crypto.keystore import Keystore
from tests.constants import (
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_ETH_PROVIDER_URI,
    MOCK_IP_ADDRESS,
)

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
    "mock_registry_sources", "monkeypatch_get_staking_provider_from_operator"
)
@pytest.mark.parametrize("character,configuration", characters_and_configurations)
def test_development_character_configurations(
    character, configuration, mocker, testerchain
):
    params = dict(
        dev_mode=True,
        lonely=True,
        domain=TEMPORARY_DOMAIN,
        checksum_address=testerchain.unassigned_accounts[0],
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
        polygon_endpoint=MOCK_ETH_PROVIDER_URI,
    )
    if character is Ursula:
        params.update(dict(operator_address=testerchain.unassigned_accounts[0]))
    config = configuration(**params)

    assert config.is_me is True
    assert config.dev_mode is True
    assert config.keystore == NO_KEYSTORE_ATTACHED

    # Production
    thing_one = config()

    # Alternate way to produce a character with a direct call
    thing_two = config.produce()
    assert isinstance(thing_two, character)

    # Ensure we do in fact have a character here
    assert isinstance(thing_one, character)

    # Ethereum Address
    assert len(thing_one.checksum_address) == 42

    # Domain
    assert TEMPORARY_DOMAIN == thing_one.domain

    # Node Storage
    assert isinstance(thing_one.node_storage, ForgetfulNodeStorage)
    assert ":memory:" in thing_one.node_storage._name

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
    fake_address = "0xdeadbeef"
    domain = TEMPORARY_DOMAIN

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
        # special case for rest_host & dev mode
        # use keystore
        keystore = Keystore.generate(
            password=INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=tmpdir
        )
        keystore.signing_public_key = SecretKey.random().public_key()
        character_config = configuration_class(
            checksum_address=fake_address,
            eth_endpoint=MOCK_ETH_PROVIDER_URI,
            domain=domain,
            rest_host=MOCK_IP_ADDRESS,
            polygon_endpoint=MOCK_ETH_PROVIDER_URI,
            policy_registry=test_registry,
            keystore=keystore,
        )

    else:
        character_config = configuration_class(
            checksum_address=fake_address,
            eth_endpoint=MOCK_ETH_PROVIDER_URI,
            domain=domain,
            policy_registry=test_registry,
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
        checksum_address=testerchain.unassigned_accounts[0],
        operator_address=testerchain.unassigned_accounts[1],
        domain=TEMPORARY_DOMAIN,
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
        polygon_endpoint=MOCK_ETH_PROVIDER_URI,
    )
    assert config.is_me is True
    assert config.dev_mode is True
    assert config.keystore == NO_KEYSTORE_ATTACHED

    # Produce an Ursula
    ursula_one = config()

    # Ensure we do in fact have an Ursula here
    assert isinstance(ursula_one, Ursula)
    assert len(ursula_one.checksum_address) == 42

    # A Temporary Ursula
    port = ursula_one.rest_information()[0].port
    assert port == UrsulaConfiguration.DEFAULT_DEVELOPMENT_REST_PORT
    assert ursula_one.certificate_filepath is CERTIFICATE_NOT_SAVED
    assert isinstance(ursula_one.node_storage, ForgetfulNodeStorage)
    assert ":memory:" in ursula_one.node_storage._name

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


@pytest.mark.skip("See #2016")
def test_destroy_configuration(config, test_emitter, capsys, mocker):
    # Setup
    config_file = config.filepath

    # Isolate from filesystem and Spy on the methods we're testing here
    spy_keystore_attached = mocker.spy(CharacterConfiguration, "attach_keystore")
    mock_config_destroy = mocker.patch.object(CharacterConfiguration, "destroy")
    spy_keystore_destroy = mocker.spy(Keystore, "destroy")
    mock_os_remove = mocker.patch("pathlib.Path.unlink")

    # Test
    destroy_configuration(emitter=test_emitter, character_config=config)

    mock_config_destroy.assert_called_once()
    captured = capsys.readouterr()
    assert SUCCESSFUL_DESTRUCTION in captured.out

    spy_keystore_attached.assert_called_once()
    spy_keystore_destroy.assert_called_once()
    mock_os_remove.assert_called_with(str(config_file))

    # Ensure all destroyed files belong to this Ursula
    for call in mock_os_remove.call_args_list:
        filepath = str(call.args[0])
        assert config.checksum_address in filepath

    expected_removal = 7  # TODO: Source this number from somewhere else

    assert mock_os_remove.call_count == expected_removal
