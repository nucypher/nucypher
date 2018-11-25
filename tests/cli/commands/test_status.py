"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import os

from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD, MOCK_CUSTOM_INSTALLATION_PATH, \
    MOCK_IP_ADDRESS_2


def test_initialize_configuration_files_and_directories(custom_filepath, click_runner):
    init_args = ('ursula', 'init', '--config-root', custom_filepath)

    # Use a custom local filepath for configuration
    user_input = '{ip}\n{password}\n{password}\n'.format(password=INSECURE_DEVELOPMENT_PASSWORD, ip=MOCK_IP_ADDRESS_2)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # CLI Output
    assert MOCK_CUSTOM_INSTALLATION_PATH in result.output, "Configuration not in system temporary directory"
    assert "nucypher ursula run" in result.output, 'Help message is missing suggested command'

    # Files and Directories
    assert os.path.isdir(custom_filepath), 'Configuration file does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'keyring')), 'Keyring does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'known_nodes')), 'known_nodes directory does not exist'

    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    # Auth
    assert 'Enter keyring password:' in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_empty_federated_status(click_runner, custom_filepath):

    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    status_args = ('status', '--config-file', custom_config_filepath)
    result = click_runner.invoke(nucypher_cli, status_args, catch_exceptions=False)

    assert result.exit_code == 0

    assert 'Federated Only' in result.output
    heading = 'Known Nodes (connected 0 / seen 0)           Last Seen    self   | known  | seednode |'
    assert heading in result.output
    assert 'password' not in result.output
