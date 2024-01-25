import json
from pathlib import Path

import pytest
from eth_account.hdaccount import Mnemonic
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
        keystore = Keystore.from_mnemonic(
            mnemonic=Mnemonic('english').generate(24),
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
