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
from instapy_chromedriver import binary_path
from selenium.webdriver.chrome.options import Options
from twisted.logger import globalLogPublisher

from nucypher.characters.control.emitters import WebEmitter
from nucypher.cli.config import NucypherClickConfig
from nucypher.utilities.logging import GlobalConsoleLogger, logToSentry
# Logger Configuration
#
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD

globalLogPublisher.removeObserver(logToSentry)

# Disable click sentry and file logging
NucypherClickConfig.log_to_sentry = False
NucypherClickConfig.log_to_file = True

# Crash on server error by default
WebEmitter._crash_on_error_default = False


##########################################

@pytest.fixture(autouse=True, scope='session')
def __very_pretty_and_insecure_scrypt_do_not_use():
    """
    # WARNING: DO NOT USE THIS CODE ANYWHERE #

    Mocks Scrypt derivation function for the duration of
    the test session in order to improve test performance.
    """

    # Capture Scrypt derivation method
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    original_derivation_function = Scrypt.derive

    # One-Time Insecure Password
    insecure_password = bytes(INSECURE_DEVELOPMENT_PASSWORD, encoding='utf8')

    # Patch Method
    def __insecure_derive(*args, **kwargs):
        """Temporarily replaces Scrypt.derive for mocking"""
        return insecure_password

    # Disable Scrypt KDF
    Scrypt.derive = __insecure_derive
    yield

    # Re-Enable Scrypt KDF
    Scrypt.derive = original_derivation_function

############################################


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


# pytest-dash selenium hook
def pytest_setup_selenium(driver_name):
    options = Options()
    options.add_argument('--window-size=1920,1080')  # required to make elements visible to selenium
    options.add_argument('--start-maximized')
    options.add_argument('--headless')
    return {
        'executable_path': binary_path,
        'options': options,
    }
