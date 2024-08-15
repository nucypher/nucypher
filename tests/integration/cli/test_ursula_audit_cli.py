import json

from mnemonic import Mnemonic

from nucypher.cli.main import nucypher_cli
from nucypher.crypto.keystore import Keystore
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD


def setup_ursula_config_file(custom_filepath, ursula_test_config, config_filename):
    keystore = Keystore.generate(
        INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=custom_filepath
    )
    keystore.unlock(INSECURE_DEVELOPMENT_PASSWORD)

    # update keystore path in config file
    ursula_config_file = custom_filepath / config_filename
    config_values = json.loads(ursula_test_config.serialize())
    config_values["keystore_path"] = str(keystore.keystore_path.resolve())
    with open(ursula_config_file, "w") as f:
        json.dump(config_values, f)

    return keystore, ursula_config_file


def test_ursula_audit_config_file_incorrect_password(
    click_runner, ursula_test_config, custom_filepath
):
    keystore, ursula_config_file = setup_ursula_config_file(
        custom_filepath, ursula_test_config, "ursula-audit-incorrect-password.json"
    )

    audit_args = (
        "ursula",
        "audit",
        "--config-file",
        str(ursula_config_file.resolve()),
    )

    user_input = "yadda,yadda,yadda\n"

    result = click_runner.invoke(
        nucypher_cli, audit_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code != 0, result.output
    assert "Password is incorrect" in result.output
    assert "Mnemonic" not in result.output


def test_ursula_audit_config_file_incorrect_mnemonic(
    click_runner, ursula_test_config, custom_filepath
):
    keystore, ursula_config_file = setup_ursula_config_file(
        custom_filepath, ursula_test_config, "ursula-audit-incorrect-mnemonic.json"
    )
    mnemonic = keystore.get_mnemonic()

    audit_args = (
        "ursula",
        "audit",
        "--config-file",
        str(ursula_config_file.resolve()),
    )

    incorrect_mnemonic = Mnemonic("english").generate(256)
    assert incorrect_mnemonic != mnemonic

    user_input = f"{INSECURE_DEVELOPMENT_PASSWORD}\n" + f"{incorrect_mnemonic}\n"

    result = click_runner.invoke(
        nucypher_cli, audit_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code != 0, result.output
    assert "Password is correct" in result.output
    assert "Mnemonic is incorrect" in result.output


def test_ursula_audit_specific_config_file(
    click_runner,
    custom_filepath,
    ursula_test_config,
):
    keystore, ursula_config_file = setup_ursula_config_file(
        custom_filepath, ursula_test_config, "ursula-audit.json"
    )
    mnemonic = keystore.get_mnemonic()

    # specific config file
    audit_args = (
        "ursula",
        "audit",
        "--config-file",
        str(ursula_config_file.resolve()),
    )

    user_input = f"{INSECURE_DEVELOPMENT_PASSWORD}\n" + f"{mnemonic}\n"

    result = click_runner.invoke(
        nucypher_cli, audit_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert "Password is correct" in result.output
    assert "Mnemonic is correct" in result.output


def test_ursula_audit_default_config_file(
    click_runner, mocker, ursula_test_config, custom_filepath
):

    keystore, ursula_config_file = setup_ursula_config_file(
        custom_filepath, ursula_test_config, "ursula-audit-default.json"
    )
    mocker.patch(
        "nucypher.cli.commands.ursula.DEFAULT_CONFIG_FILEPATH", ursula_config_file
    )

    mnemonic = keystore.get_mnemonic()

    # default config file
    audit_args = (
        "ursula",
        "audit",
    )

    user_input = f"{INSECURE_DEVELOPMENT_PASSWORD}\n" + f"{mnemonic}\n"

    result = click_runner.invoke(
        nucypher_cli, audit_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert "Password is correct" in result.output
    assert "Mnemonic is correct" in result.output


def test_ursula_audit_view_mnemonic_config_file(
    click_runner, ursula_test_config, custom_filepath
):
    keystore, ursula_config_file = setup_ursula_config_file(
        custom_filepath, ursula_test_config, "ursula-audit-view-mnemonic.json"
    )
    mnemonic = keystore.get_mnemonic()

    # view mnemonic
    audit_args = (
        "ursula",
        "audit",
        "--config-file",
        str(ursula_config_file.resolve()),
        "--view-mnemonic",
    )

    user_input = f"{INSECURE_DEVELOPMENT_PASSWORD}\n"

    result = click_runner.invoke(
        nucypher_cli, audit_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert "Password is correct" in result.output
    assert mnemonic in result.output


def test_ursula_audit_keystore_file_incorrect_password(click_runner, custom_filepath):
    keystore = Keystore.generate(
        INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=custom_filepath
    )
    keystore.unlock(INSECURE_DEVELOPMENT_PASSWORD)

    audit_args = (
        "ursula",
        "audit",
        "--keystore-filepath",
        str(keystore.keystore_path.resolve()),
    )

    user_input = "yadda,yadda,yadda\n"

    result = click_runner.invoke(
        nucypher_cli, audit_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code != 0, result.output
    assert "Password is incorrect" in result.output
    assert "Mnemonic" not in result.output


def test_ursula_audit_keystore_file_incorrect_mnemonic(click_runner, custom_filepath):
    keystore = Keystore.generate(
        INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=custom_filepath
    )
    keystore.unlock(INSECURE_DEVELOPMENT_PASSWORD)
    mnemonic = keystore.get_mnemonic()

    audit_args = (
        "ursula",
        "audit",
        "--keystore-filepath",
        str(keystore.keystore_path.resolve()),
    )

    incorrect_mnemonic = Mnemonic("english").generate(256)
    assert incorrect_mnemonic != mnemonic

    user_input = f"{INSECURE_DEVELOPMENT_PASSWORD}\n" + f"{incorrect_mnemonic}\n"

    result = click_runner.invoke(
        nucypher_cli, audit_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code != 0, result.output
    assert "Password is correct" in result.output
    assert "Mnemonic is incorrect" in result.output


def test_ursula_audit_keystore_file(click_runner, custom_filepath):

    keystore = Keystore.generate(
        INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=custom_filepath
    )
    keystore.unlock(INSECURE_DEVELOPMENT_PASSWORD)
    mnemonic = keystore.get_mnemonic()

    audit_args = (
        "ursula",
        "audit",
        "--keystore-filepath",
        str(keystore.keystore_path.resolve()),
    )

    user_input = f"{INSECURE_DEVELOPMENT_PASSWORD}\n" + f"{mnemonic}\n"

    result = click_runner.invoke(
        nucypher_cli, audit_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert "Password is correct" in result.output
    assert "Mnemonic is correct" in result.output


def test_ursula_audit_view_mnemonic_keystore_file(click_runner, custom_filepath):
    keystore = Keystore.generate(
        INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=custom_filepath
    )
    keystore.unlock(INSECURE_DEVELOPMENT_PASSWORD)
    mnemonic = keystore.get_mnemonic()

    audit_args = (
        "ursula",
        "audit",
        "--keystore-filepath",
        str(keystore.keystore_path.resolve()),
        "--view-mnemonic",
    )

    user_input = f"{INSECURE_DEVELOPMENT_PASSWORD}\n"

    result = click_runner.invoke(
        nucypher_cli, audit_args, input=user_input, catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert "Password is correct" in result.output
    assert mnemonic in result.output
