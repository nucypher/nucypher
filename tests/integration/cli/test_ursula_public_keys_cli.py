import json

from nucypher.cli.main import nucypher_cli
from nucypher.crypto.keystore import Keystore
from nucypher.crypto.powers import RitualisticPower
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD


def test_ursula_public_keys_invalid(click_runner, ursula_test_config, custom_filepath):
    keystore = Keystore.generate(
        INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=custom_filepath
    )

    ursula_config_file = custom_filepath / "ursula-test.json"
    ursula_test_config._write_configuration_file(filepath=ursula_config_file)

    expected_error = "At most, one of --keystore-filepath, --config-file, or --from-mnemonic must be specified"

    # config-file and keystore-filepath
    public_keys_args = (
        "ursula",
        "public-keys",
        "--config-file",
        str(ursula_config_file.resolve()),
        "--keystore-filepath",
        str(keystore.keystore_path.resolve()),
    )

    result = click_runner.invoke(nucypher_cli, public_keys_args, catch_exceptions=False)
    assert result.exit_code != 0
    assert expected_error in result.output

    # config-file and from-mnemonic
    public_keys_args = (
        "ursula",
        "public-keys",
        "--config-file",
        str(ursula_config_file.resolve()),
        "--from-mnemonic",
    )

    result = click_runner.invoke(nucypher_cli, public_keys_args, catch_exceptions=False)
    assert result.exit_code != 0
    assert expected_error in result.output

    # keystore-filepath and from-mnemonic
    public_keys_args = (
        "ursula",
        "public-keys",
        "--keystore-filepath",
        str(keystore.keystore_path.resolve()),
        "--from-mnemonic",
    )

    result = click_runner.invoke(nucypher_cli, public_keys_args, catch_exceptions=False)
    assert result.exit_code != 0
    assert expected_error in result.output

    # all 3 values - config-file, keystore-filepath, from-mnemonic
    public_keys_args = (
        "ursula",
        "public-keys",
        "--config-file",
        str(ursula_config_file.resolve()),
        "--keystore-filepath",
        str(keystore.keystore_path.resolve()),
        "--from-mnemonic",
    )

    result = click_runner.invoke(nucypher_cli, public_keys_args, catch_exceptions=False)
    assert result.exit_code != 0
    assert expected_error in result.output


def test_ursula_public_keys_derived_ferveo_key(
    click_runner, mocker, ursula_test_config, custom_filepath
):
    keystore = Keystore.generate(
        INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=custom_filepath
    )
    keystore.unlock(INSECURE_DEVELOPMENT_PASSWORD)

    power = keystore.derive_crypto_power(RitualisticPower)
    expected_public_key = power.public_key()
    expected_public_key_hex = bytes(expected_public_key).hex()

    public_keys_args = (
        "ursula",
        "public-keys",
        "--keystore-filepath",
        str(keystore.keystore_path.resolve()),
    )

    user_input = f"{INSECURE_DEVELOPMENT_PASSWORD}\n"

    result = click_runner.invoke(
        nucypher_cli, public_keys_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert expected_public_key_hex in result.output

    # using config file produces same key
    config_values = json.loads(ursula_test_config.serialize())
    config_values["keystore_path"] = str(keystore.keystore_path.resolve())
    updated_config_file = custom_filepath / "updated-ursula.json"
    with open(updated_config_file, "w") as f:
        json.dump(config_values, f)

    public_keys_args = (
        "ursula",
        "public-keys",
        "--config-file",
        str(updated_config_file.resolve()),
    )
    user_input = f"{INSECURE_DEVELOPMENT_PASSWORD}\n"

    result = click_runner.invoke(
        nucypher_cli, public_keys_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert expected_public_key_hex in result.output

    # using default config filepath - no values provided
    mocker.patch(
        "nucypher.cli.commands.ursula.DEFAULT_CONFIG_FILEPATH", updated_config_file
    )
    public_keys_args = (
        "ursula",
        "public-keys",
    )
    user_input = f"{INSECURE_DEVELOPMENT_PASSWORD}\n"

    result = click_runner.invoke(
        nucypher_cli, public_keys_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert expected_public_key_hex in result.output

    # using mnemonic produces same key
    words = keystore.get_mnemonic()

    public_keys_args = (
        "ursula",
        "public-keys",
        "--from-mnemonic",
    )
    user_input = f"{words}\n"
    result = click_runner.invoke(
        nucypher_cli, public_keys_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert expected_public_key_hex in result.output
