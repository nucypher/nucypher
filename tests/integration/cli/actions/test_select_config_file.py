from unittest.mock import patch

import click
import pytest

from nucypher.cli.actions.select import select_config_file
from nucypher.cli.literature import (
    DEFAULT_TO_LONE_CONFIG_FILE,
    IGNORE_OLD_CONFIGURATION,
    MIGRATE_OLD_CONFIGURATION,
    NO_CONFIGURATIONS_ON_DISK,
    PROMPT_TO_MIGRATE,
)


def test_select_config_file_with_no_config_files(
    test_emitter, capsys, alice_test_config, temp_dir_path
):

    # Setup
    config_class = alice_test_config

    # Prove there are no config files on the disk.
    assert not list(temp_dir_path.iterdir())
    with pytest.raises(click.Abort):
        select_config_file(emitter=test_emitter,
                           config_class=config_class,
                           config_root=temp_dir_path)

    # Ensure we notified the user accurately.
    captured = capsys.readouterr()
    message = NO_CONFIGURATIONS_ON_DISK.format(name=config_class.NAME.capitalize(),
                                               command=config_class.NAME)
    assert message in captured.out


def test_auto_select_config_file(
    test_emitter, capsys, alice_test_config, temp_dir_path, mock_stdin
):
    """Only one configuration was found, so it was chosen automatically"""

    config_class = alice_test_config
    config_path = temp_dir_path / config_class.generate_filename()

    # Make one configuration
    config_class.to_configuration_file(filepath=config_path)
    assert config_path.exists()

    result = select_config_file(emitter=test_emitter,
                                config_class=config_class,
                                config_root=temp_dir_path)

    # ... ensure the correct account was selected
    assert result == config_path

    # ... the user was *not* prompted
    # If they were, `mock_stdin` would complain.

    # ...nothing was displayed
    captured = capsys.readouterr()
    assert DEFAULT_TO_LONE_CONFIG_FILE.format(config_class=config_class.NAME.capitalize(),
                                              config_file=str(config_path)) in captured.out


def test_confirm_prompt_to_migrate_select_config_file(
    test_emitter, capsys, alice_test_config, temp_dir_path, mock_stdin
):
    config_class = alice_test_config
    config_path = temp_dir_path / config_class.generate_filename()
    # Make one configuration
    config_class.to_configuration_file(filepath=config_path, override=True)
    assert config_path.exists()

    old_version = config_class.VERSION - 1
    mock_stdin.line("Y")
    with patch.object(
        config_class,
        "address_from_filepath",
        side_effect=[
            config_class.OldVersion(old_version, "too old"),
            alice_test_config.checksum_address,
        ],
    ):
        result = select_config_file(
            emitter=test_emitter, config_class=config_class, config_root=temp_dir_path
        )

    # ... ensure the correct account was selected
    assert result == config_path

    captured = capsys.readouterr()
    assert (
        PROMPT_TO_MIGRATE.format(config_file=str(config_path), version=old_version)
        in captured.out
    )
    assert (
        MIGRATE_OLD_CONFIGURATION.format(
            config_file=str(config_path), version=old_version
        )
        in captured.out
    )
    assert (
        DEFAULT_TO_LONE_CONFIG_FILE.format(
            config_class=config_class.NAME.capitalize(), config_file=str(config_path)
        )
        in captured.out
    )


def test_deny_prompt_to_migrate_select_config_file(
    test_emitter, capsys, alice_test_config, temp_dir_path, mock_stdin
):
    config_class = alice_test_config
    config_path = temp_dir_path / config_class.generate_filename()

    # Make one configuration
    config_class.to_configuration_file(filepath=config_path, override=True)
    assert config_path.exists()

    old_version = config_class.VERSION - 1
    mock_stdin.line("N")
    # expect abort because no configuration files available
    with pytest.raises(click.Abort):
        with patch.object(
            config_class,
            "address_from_filepath",
            side_effect=[
                config_class.OldVersion(old_version, "too old"),
                alice_test_config.checksum_address,
            ],
        ):
            _ = select_config_file(
                emitter=test_emitter,
                config_class=config_class,
                config_root=temp_dir_path,
            )

    captured = capsys.readouterr()
    assert (
        PROMPT_TO_MIGRATE.format(config_file=str(config_path), version=old_version)
        in captured.out
    )
    assert (
        IGNORE_OLD_CONFIGURATION.format(
            config_file=str(config_path), version=old_version
        )
        in captured.out
    )
    assert (
        NO_CONFIGURATIONS_ON_DISK.format(
            name=config_class.NAME.capitalize(), command=config_class.NAME
        )
        in captured.out
    )

    assert (
        MIGRATE_OLD_CONFIGURATION.format(
            config_file=str(config_path), version=old_version
        )
        not in captured.out
    )


def test_dont_prompt_to_migrate_select_config_file(
    test_emitter, capsys, alice_test_config, temp_dir_path, mock_stdin
):
    """Only one configuration was found, so it was chosen automatically"""
    config_class = alice_test_config
    config_path = temp_dir_path / config_class.generate_filename()

    # Make one configuration
    config_class.to_configuration_file(filepath=config_path, override=True)
    assert config_path.exists()

    old_version = config_class.VERSION - 1
    with patch.object(
        config_class,
        "address_from_filepath",
        side_effect=[
            config_class.OldVersion(old_version, "too old"),
            alice_test_config.checksum_address,
        ],
    ):
        result = select_config_file(
            emitter=test_emitter,
            config_class=config_class,
            config_root=temp_dir_path,
            do_auto_migrate=True,
        )

    # ... ensure the correct account was selected
    assert result == config_path

    # ... the user was *not* prompted
    # If they were, `mock_stdin` would complain.

    captured = capsys.readouterr()
    assert (
        PROMPT_TO_MIGRATE.format(config_file=str(config_path), version=old_version)
        not in captured.out
    )

    assert (
        MIGRATE_OLD_CONFIGURATION.format(
            config_file=str(config_path), version=old_version
        )
        in captured.out
    )
    assert (
        DEFAULT_TO_LONE_CONFIG_FILE.format(
            config_class=config_class.NAME.capitalize(), config_file=str(config_path)
        )
        in captured.out
    )
