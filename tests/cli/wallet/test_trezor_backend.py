import pytest
from trezorlib import client as trezor_client
from trezorlib import device as trezor_device
from trezorlib import ethereum as trezor_eth
from trezorlib.messages import EthereumMessageSignature
from trezorlib.transport import TransportException
from usb1 import USBErrorNoDevice, USBErrorBusy

from nucypher.cli.hardware.backends import Trezor
from nucypher.crypto.signing import InvalidSignature


fake_signature = b"2\xcf?IZ\x9b\x99\x81\xff\xfb\xe2\xf1\x8a\xba\n\xc2\x18\x87nE\xa1\xa2C\xcc\x93+\xef\xe3M0\xed=F\xeaR8,)'\xe9\x83\x92I\x06\xa8\xcdz\xaazn\\\xf9>\xd7h\x1c\x0c\xffC\xdb\x8b\xe5\xa4V\x1c"
fake_address = '0xE67d36f4063eEd7a3464D243752669b6503883f8'
fake_message = b'test'


@pytest.fixture()
def mock_trezorlib(mocker):

    trezor_client.get_default_client = lambda: None

    # trezorlib.ethereum mock functions
    def mocked_sign_message(client, bip44_path, message):

        return EthereumMessageSignature(
                signature=fake_signature,
                address=fake_address)

    def mocked_verify_message(client, address, signature, message):
        if (address != fake_address or signature != fake_signature or
                message != fake_message):
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


def test_trezor_defaults(mock_trezorlib):
    trezor_backend = Trezor()

    assert trezor_backend.DEFAULT_BIP44_PATH == "m/44'/60'/0'/0"
    assert trezor_backend._Trezor__bip44_path == [2147483692, 2147483708,
                                                  2147483648, 0]

    def fail_get_default_client():
        raise TransportException("No device found...")

    trezor_client.get_default_client = fail_get_default_client
    with pytest.raises(RuntimeError):
        Trezor()
    trezor_client.get_default_client = lambda: None


def test_trezor_call_handler_decorator_errors(mock_trezorlib):
    trezor_backend = Trezor()

    def raises_usb_no_device_error(mock_self):
        raise USBErrorNoDevice("No device!")

    def raises_usb_busy_error(mock_self):
        raise USBErrorBusy("Device busy!")

    def raises_no_error(mock_self):
        return 'success'

    with pytest.raises(Trezor.DeviceError):
        Trezor._handle_device_call(raises_usb_no_device_error)(trezor_backend)

    with pytest.raises(Trezor.DeviceError):
        Trezor._handle_device_call(raises_usb_busy_error)(trezor_backend)

    result = Trezor._handle_device_call(raises_no_error)(trezor_backend)
    assert 'success' == result


def test_trezor_sign_and_verify(mock_trezorlib):
    trezor_backend = Trezor()

    test_sig = trezor_backend.sign_message(b'test')
    assert test_sig.signature == fake_signature
    assert test_sig.address == fake_address

    assert trezor_backend.verify_message(test_sig.signature, b'test',
                                         test_sig.address)

    with pytest.raises(InvalidSignature):
        trezor_backend.verify_message(test_sig.signature, b'bad message',
                                      test_sig.address)
