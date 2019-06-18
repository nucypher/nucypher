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
import sys
from trezorlib import client as trezor_client
from trezorlib import device as trezor_device
from trezorlib import ethereum as trezor_eth
from trezorlib.messages import EthereumMessageSignature
from twisted.logger import globalLogPublisher

from nucypher.characters.control.emitters import WebEmitter
from nucypher.cli.config import NucypherClickConfig
from nucypher.utilities.logging import GlobalConsoleLogger, logToSentry
# Logger Configuration
#
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD


# CI machines don't have libusb available, thus usb1 raises an OSError.
# This is a hack around that so we can patch what we need to run on CI.
try:
    import usb1
except OSError:
    class mock_usb1:

        class USBErrorNoDevice(Exception):
            pass

        class USBErrorBusy(Exception):
            pass

    usb1 = mock_usb1()
    sys.modules['usb1'] = usb1


# Disable click sentry and file logging
globalLogPublisher.removeObserver(logToSentry)
NucypherClickConfig.log_to_sentry = False

# Log to files
NucypherClickConfig.log_to_file = True

# Crash on server error by default
WebEmitter._crash_on_error_default = True


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

    #
    # Handle slow tests marker
    #

    if not config.getoption("--runslow"):  # --runslow given in cli: do not skip slow tests
        skip_slow = pytest.mark.skip(reason="need --runslow option to run")

        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)

    #
    # Handle Log Level
    #

    log_level_name = config.getoption("--log-level", "info", skip=True)

    GlobalConsoleLogger.set_log_level(log_level_name)


@pytest.fixture()
def fake_trezor_signature():
    return b"2\xcf?IZ\x9b\x99\x81\xff\xfb\xe2\xf1\x8a\xba\n\xc2\x18\x87nE\xa1\xa2C\xcc\x93+\xef\xe3M0\xed=F\xeaR8,)'\xe9\x83\x92I\x06\xa8\xcdz\xaazn\\\xf9>\xd7h\x1c\x0c\xffC\xdb\x8b\xe5\xa4V\x1c"


@pytest.fixture()
def fake_trezor_address():
    return '0xE67d36f4063eEd7a3464D243752669b6503883f8'


@pytest.fixture()
def fake_trezor_message():
    return b'test'


@pytest.fixture()
def mock_trezorlib(mocker,
                   fake_trezor_signature,
                   fake_trezor_address,
                   fake_trezor_message):
    trezor_client.get_default_client = lambda: None

    # trezorlib.ethereum mock functions
    def mocked_sign_message(client, bip44_path, message):

        return EthereumMessageSignature(
                signature=fake_trezor_signature,
                address=fake_trezor_address)

    def mocked_verify_message(client, address, signature, message):
        if (address != fake_trezor_address or
                signature != fake_trezor_signature or
                message != fake_trezor_message):
            return False
        return True

    # trezorlib.device mock functions
    def mocked_wipe(client):
        return 'Device wiped'

    ethereum_mock_load = {
            'sign_message': mocked_sign_message,
            'verify_message': mocked_verify_message,
    }

    device_mock_load = {
            'wipe': mocked_wipe,
    }

    for method, patch in ethereum_mock_load.items():
        mocker.patch.object(trezor_eth, method, patch)

    for method, patch in device_mock_load.items():
        mocker.patch.object(trezor_device, method, patch)
