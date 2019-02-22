"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import pytest
from twisted.logger import globalLogPublisher

from nucypher.characters.control.wsgi import WSGIController
from nucypher.cli.config import NucypherClickConfig
from nucypher.utilities.logging import GlobalConsoleLogger, logToSentry

# Logger Configuration
#
globalLogPublisher.removeObserver(logToSentry)

# Disable click sentry and file logging
NucypherClickConfig.log_to_sentry = False
NucypherClickConfig.log_to_file = False

# Crash on server error by default
WSGIController._crash_on_error_default = False


#
# Pytest configuration
#

pytest_plugins = [
    'tests.fixtures',  # Includes external fixtures module
]


def pytest_addoption(parser):
    parser.addoption("--runslow",
                     action="store_true",
                     default=False,
                     help="run tests even if they are marked as slow")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--runslow"):  # --runslow given in cli: do not skip slow tests
        skip_slow = pytest.mark.skip(reason="need --runslow option to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
    log_level_name = config.getoption("--log-level", "info", skip=True)
    GlobalConsoleLogger.set_log_level(log_level_name)
