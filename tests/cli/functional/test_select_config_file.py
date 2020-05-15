from pathlib import Path

import os

import click
import pytest

from nucypher.cli.actions.select import select_config_file
from nucypher.cli.literature import NO_CONFIGURATIONS_ON_DISK


def test_select_config_file_with_no_config_files(test_emitter,
                                                 stdout_trap,
                                                 alice_blockchain_test_config,
                                                 tmpdir):

    # Setup
    config_class = alice_blockchain_test_config

    # Prove there are no config files on the disk.
    assert not os.listdir(tmpdir)
    with pytest.raises(click.Abort):
        select_config_file(emitter=test_emitter,
                           config_class=config_class,
                           config_root=tmpdir)

    # Ensure we notified the user accurately.
    output = stdout_trap.getvalue()
    message = NO_CONFIGURATIONS_ON_DISK.format(name=config_class.NAME.capitalize(),
                                               command=config_class.NAME)
    assert message in output


def test_auto_select_config_file(test_emitter,
                                 stdout_trap,
                                 alice_blockchain_test_config,
                                 tmpdir,
                                 mock_click_prompt):
    """Only one configuration was found, so it was chosen automatically"""

    config_class = alice_blockchain_test_config
    config_path = Path(tmpdir) / config_class.generate_filename()

    # Make one configuration
    config_class.to_configuration_file(filepath=config_path)
    assert config_path.exists()

    result = select_config_file(emitter=test_emitter,
                                config_class=config_class,
                                config_root=tmpdir)

    # ... ensure the correct account was selected
    assert result == str(config_path)

    # ... the user was *not* prompted
    mock_click_prompt.assert_not_called()

    # ...nothing was displayed
    output = stdout_trap.getvalue()
    assert not output


def test_interactive_select_config_file(test_emitter,
                                        stdout_trap,
                                        alice_blockchain_test_config,
                                        tmpdir,
                                        mock_click_prompt,
                                        mock_accounts):

    """Multiple configurations found - Prompt the user for a selection"""

    user_input = 0
    config = alice_blockchain_test_config
    config_class = config.__class__

    # Make one configuration...
    config_path = Path(tmpdir) / config_class.generate_filename()
    config.to_configuration_file(filepath=config_path)
    assert config_path.exists()
    select_config_file(emitter=test_emitter,
                       config_class=config_class,
                       config_root=tmpdir)

    # ... and then a bunch more
    accounts = list(mock_accounts.items())
    filenames = dict()
    for filename, account in accounts:
        config.checksum_address = account.address
        config_path = Path(tmpdir) / config.generate_filename(modifier=account.address)
        path = config.to_configuration_file(filepath=config_path, modifier=account.address)
        filenames[path] = account.address
        assert config_path.exists()

    mock_click_prompt.return_value = user_input
    result = select_config_file(emitter=test_emitter,
                                config_class=config_class,
                                config_root=tmpdir)

    output = stdout_trap.getvalue()
    for filename, account in accounts:
        assert account.address in output

    table_data = output.split('\n')
    table_body = [tuple(row.split()) for row in table_data[2:-1]]

    for index, (filename, account) in enumerate(accounts):
        assert False

    selection = config.filepath
    assert isinstance(result, str)
    result = Path(result)
    assert result.exists()
    assert result == selection
