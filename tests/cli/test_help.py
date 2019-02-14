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


from nucypher.cli.deploy import deploy
from nucypher.cli.main import nucypher_cli


def test_nucypher_help_message(click_runner):
    help_args = ('--help', )
    result = click_runner.invoke(nucypher_cli, help_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert '[OPTIONS] COMMAND [ARGS]' in result.output, 'Missing or invalid help text was produced.'


def test_nucypher_ursula_help_message(click_runner):
    help_args = ('ursula', '--help')
    result = click_runner.invoke(nucypher_cli, help_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert 'ursula [OPTIONS] ACTION' in result.output, 'Missing or invalid help text was produced.'


def test_nucypher_deploy_help_message(click_runner):
    help_args = ('--help', )
    result = click_runner.invoke(deploy, help_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert 'deploy [OPTIONS] ACTION' in result.output, 'Missing or invalid help text was produced.'
