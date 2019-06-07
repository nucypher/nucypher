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


import contextlib
import json
import os
import shutil
import sys

import pytest
from click.testing import CliRunner
from trezorlib import client as trezor_client
from trezorlib import device as trezor_device
from trezorlib import ethereum as trezor_eth
from trezorlib.messages import EthereumMessageSignature

from nucypher.blockchain.eth.registry import AllocationRegistry
from nucypher.config.characters import UrsulaConfiguration
from nucypher.utilities.sandbox.constants import (
    MOCK_CUSTOM_INSTALLATION_PATH,
    MOCK_ALLOCATION_INFILE,
    MOCK_REGISTRY_FILEPATH,
    ONE_YEAR_IN_SECONDS)
from nucypher.utilities.sandbox.constants import MOCK_CUSTOM_INSTALLATION_PATH_2, INSECURE_DEVELOPMENT_PASSWORD


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


@pytest.fixture(scope='module')
def click_runner():
    runner = CliRunner()
    yield runner


@pytest.fixture(scope='session')
def deploy_user_input():
    account_index = '0\n'
    yes = 'Y\n'
    deployment_secret = f'{INSECURE_DEVELOPMENT_PASSWORD}\n'
    user_input = account_index + yes + (deployment_secret * 8) + 'DEPLOY'
    return user_input


@pytest.fixture(scope='session')
def nominal_federated_configuration_fields():
    config = UrsulaConfiguration(dev_mode=True, federated_only=True)
    config_fields = config.static_payload()
    yield tuple(config_fields.keys())
    del config


@pytest.fixture(scope='module')
def mock_allocation_infile(testerchain, token_economics):
    accounts = testerchain.unassigned_accounts
    allocation_data = [{'address': addr,
                        'amount': token_economics.minimum_allowed_locked,
                        'duration': ONE_YEAR_IN_SECONDS}
                       for addr in accounts]

    with open(MOCK_ALLOCATION_INFILE, 'w') as file:
        file.write(json.dumps(allocation_data))

    registry = AllocationRegistry(registry_filepath=MOCK_ALLOCATION_INFILE)
    yield registry
    os.remove(MOCK_ALLOCATION_INFILE)


@pytest.fixture(scope='module', autouse=True)
def mock_primary_registry_filepath():
    yield MOCK_REGISTRY_FILEPATH
    if os.path.isfile(MOCK_REGISTRY_FILEPATH):
        os.remove(MOCK_REGISTRY_FILEPATH)


@pytest.fixture(scope='module')
def custom_filepath():
    _custom_filepath = MOCK_CUSTOM_INSTALLATION_PATH
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(_custom_filepath, ignore_errors=True)
    try:
        yield _custom_filepath
    finally:
        with contextlib.suppress(FileNotFoundError):
            shutil.rmtree(_custom_filepath, ignore_errors=True)


@pytest.fixture(scope='module')
def custom_filepath_2():
    _custom_filepath = MOCK_CUSTOM_INSTALLATION_PATH_2
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(_custom_filepath, ignore_errors=True)
    try:
        yield _custom_filepath
    finally:
        with contextlib.suppress(FileNotFoundError):
            shutil.rmtree(_custom_filepath, ignore_errors=True)


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
def mock_trezorlib(mocker, fake_trezor_signature, fake_trezor_address,
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

