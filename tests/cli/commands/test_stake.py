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


import pytest
from click.testing import CliRunner

from nucypher.cli.main import nucypher_cli


@pytest.mark.skip("To be implemented")  # TODO
def test_stake_init(click_runner):
    result = click_runner.invoke(nucypher_cli, ['stake', 'init'], catch_exceptions=False)


@pytest.mark.skip("To be implemented")  # TODO
def test_stake_info(click_runner):
    result = click_runner.invoke(nucypher_cli, ['stake', 'info'], catch_exceptions=False)


@pytest.mark.skip("To be implemented")  # TODO
def test_stake_confirm(click_runner):
    result = click_runner.invoke(nucypher_cli, ['stake', 'confirm-activity'], catch_exceptions=False)
