import sys

import pytest
from trezorlib import client as trezor_client
from trezorlib import device as trezor_device
from trezorlib import ethereum as trezor_eth
from trezorlib.messages import EthereumMessageSignature

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

    def mocked_get_device_id(client):
        return '000000000000'

    ethereum_mock_load = {
            'sign_message': mocked_sign_message,
            'verify_message': mocked_verify_message,
            # 'get_device_id': mocked_get_device_id,

    }

    device_mock_load = {
        'wipe': mocked_wipe,
    }

    client_mock_load = {
        'get_device_id': mocked_get_device_id,

    }

    modules_to_mock = (trezor_eth, trezor_device, trezor_client)
    mock_loads = (ethereum_mock_load, device_mock_load, client_mock_load)
    modules_and_mocks = zip(modules_to_mock, mock_loads)
    for module, mocks in modules_and_mocks:
        for method, patch in mocks.items():
            mocker.patch.object(module, method, patch)
