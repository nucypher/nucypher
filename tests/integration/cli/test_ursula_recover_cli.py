from pathlib import Path

from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.crypto.keystore import Keystore
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD, YES_ENTER


def test_ursula_recover_invalid(click_runner, ursula_test_config, custom_filepath):
    keystore = Keystore.generate(
        INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=custom_filepath
    )

    ursula_config_file = custom_filepath / "ursula-invalid-test.json"

    # no config-file - so default attempted
    recover_args = (
        "ursula",
        "recover",
        "--keystore-filepath",
        str(keystore.keystore_path.resolve()),
    )

    result = click_runner.invoke(nucypher_cli, recover_args, catch_exceptions=False)
    assert result.exit_code != 0
    assert "Ursula configuration file not found" in result.output

    # config-file does not exist
    recover_args = (
        "ursula",
        "recover",
        "--config-file",
        str(ursula_config_file.resolve()),
    )

    result = click_runner.invoke(nucypher_cli, recover_args, catch_exceptions=False)
    assert result.exit_code != 0
    assert f"'{ursula_config_file.resolve()}' does not exist" in result.output

    # create config file
    ursula_test_config._write_configuration_file(filepath=ursula_config_file)

    # keystore-filepath does not exist
    non_existent_keystore_filepath = custom_filepath / "non_existent.priv"
    recover_args = (
        "ursula",
        "recover",
        "--config-file",
        str(ursula_config_file.resolve()),
        "--keystore-filepath",
        str(non_existent_keystore_filepath.resolve()),
    )

    result = click_runner.invoke(nucypher_cli, recover_args, catch_exceptions=False)
    assert result.exit_code != 0
    assert (
        f"'{non_existent_keystore_filepath.resolve()}' does not exist" in result.output
    )


def test_ursula_recover_keystore_file(
    click_runner, mocker, ursula_test_config, custom_filepath
):
    #
    # use specific config file
    #
    keystore = Keystore.generate(
        INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=custom_filepath
    )

    ursula_config_file = custom_filepath / "ursula-keystore-test.json"
    ursula_test_config._write_configuration_file(filepath=ursula_config_file)

    recover_args = (
        "ursula",
        "recover",
        "--config-file",
        str(ursula_config_file.resolve()),
        "--keystore-filepath",
        str(keystore.keystore_path.resolve()),
    )
    user_input = f"{INSECURE_DEVELOPMENT_PASSWORD}\n"

    result = click_runner.invoke(
        nucypher_cli, recover_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code == 0
    assert str(keystore.keystore_path.resolve()) in result.output
    updated_ursula_config = UrsulaConfiguration._read_configuration_file(
        ursula_config_file
    )
    assert str(updated_ursula_config["keystore_path"].resolve()) == str(
        keystore.keystore_path.resolve()
    )
    assert str(updated_ursula_config["keystore_path"].resolve()) in result.output

    #
    # use default config file
    #
    keystore = Keystore.generate(
        INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=custom_filepath
    )

    ursula_default_file = custom_filepath / "ursula-keystore-default.json"
    ursula_test_config._write_configuration_file(filepath=ursula_default_file)
    mocker.patch(
        "nucypher.cli.commands.ursula.DEFAULT_CONFIG_FILEPATH", ursula_default_file
    )
    recover_args = (
        "ursula",
        "recover",
        "--keystore-filepath",
        str(keystore.keystore_path.resolve()),
    )

    user_input = f"{INSECURE_DEVELOPMENT_PASSWORD}\n"

    result = click_runner.invoke(
        nucypher_cli, recover_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code == 0

    updated_default_ursula_config = UrsulaConfiguration._read_configuration_file(
        ursula_default_file
    )
    assert (
        str(updated_default_ursula_config["keystore_path"].resolve()) in result.output
    )
    assert str(updated_default_ursula_config["keystore_path"].resolve()) == str(
        keystore.keystore_path.resolve()
    )


def test_ursula_recover_mnemonic(
    click_runner, mocker, ursula_test_config, custom_filepath
):
    mocker.patch(
        "nucypher.crypto.keystore.Keystore._DEFAULT_DIR", custom_filepath / "keystore"
    )

    #
    # use specific config file
    #
    keystore = Keystore.generate(
        INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=custom_filepath
    )
    keystore.unlock(INSECURE_DEVELOPMENT_PASSWORD)
    mnemonic = keystore.get_mnemonic()

    ursula_config_file = custom_filepath / "ursula-mnemonic-test.json"
    ursula_test_config._write_configuration_file(filepath=ursula_config_file)
    # could be None
    old_keystore_path = (
        UrsulaConfiguration._read_configuration_file(ursula_config_file)[
            "keystore_path"
        ]
        or Path()
    )

    recover_args = (
        "ursula",
        "recover",
        "--config-file",
        str(ursula_config_file.resolve()),
    )
    user_input = (
        YES_ENTER
        + f"{mnemonic}\n"
        + f"{INSECURE_DEVELOPMENT_PASSWORD}\n"
        + f"{INSECURE_DEVELOPMENT_PASSWORD}\n"
    )

    result = click_runner.invoke(
        nucypher_cli, recover_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code == 0
    updated_ursula_config = UrsulaConfiguration._read_configuration_file(
        ursula_config_file
    )
    assert str(updated_ursula_config["keystore_path"].resolve()) in result.output
    assert str(updated_ursula_config["keystore_path"].resolve()) != str(
        old_keystore_path.resolve()
    )

    #
    # use default config file
    #
    keystore = Keystore.generate(
        INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=custom_filepath
    )
    keystore.unlock(INSECURE_DEVELOPMENT_PASSWORD)
    mnemonic = keystore.get_mnemonic()

    ursula_default_file = custom_filepath / "ursula-mnemonic-default.json"
    mocker.patch(
        "nucypher.cli.commands.ursula.DEFAULT_CONFIG_FILEPATH", ursula_default_file
    )

    ursula_test_config._write_configuration_file(filepath=ursula_default_file)
    # could be None
    old_default_keystore_path = (
        UrsulaConfiguration._read_configuration_file(ursula_default_file)[
            "keystore_path"
        ]
        or Path()
    )

    recover_args = (
        "ursula",
        "recover",
    )

    user_input = (
        YES_ENTER
        + f"{mnemonic}\n"
        + f"{INSECURE_DEVELOPMENT_PASSWORD}\n"
        + f"{INSECURE_DEVELOPMENT_PASSWORD}\n"
    )

    result = click_runner.invoke(
        nucypher_cli, recover_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code == 0
    updated_default_ursula_config = UrsulaConfiguration._read_configuration_file(
        ursula_default_file
    )
    assert (
        str(updated_default_ursula_config["keystore_path"].resolve()) in result.output
    )
    assert str(updated_default_ursula_config["keystore_path"].resolve()) != str(
        old_default_keystore_path.resolve()
    )
