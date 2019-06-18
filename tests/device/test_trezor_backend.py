import pytest
from trezorlib import client as trezor_client
from trezorlib.transport import TransportException
from usb1 import USBErrorNoDevice, USBErrorBusy

from nucypher.crypto.signing import InvalidSignature
from nucypher.device.trezor import Trezor


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


def test_trezor_wipe(mock_trezorlib):
    trezor_backend = Trezor()

    assert 'Device wiped' == trezor_backend._reset()


def test_trezor_configure(mock_trezorlib):
    trezor_backend = Trezor()

    with pytest.raises(NotImplementedError):
        trezor_backend.configure()


def test_trezor_sign_and_verify(mock_trezorlib, fake_trezor_signature,
                                fake_trezor_address):
    trezor_backend = Trezor()

    test_sig = trezor_backend.sign_message(b'test')
    assert test_sig.signature == fake_trezor_signature
    assert test_sig.address == fake_trezor_address

    assert trezor_backend.verify_message(test_sig.signature, b'test',
                                         test_sig.address)

    with pytest.raises(InvalidSignature):
        trezor_backend.verify_message(test_sig.signature, b'bad message',
                                      test_sig.address)


def test_trezor_sign_eth_transaction(mock_trezorlib):
    trezor_backend = Trezor()

    with pytest.raises(NotImplementedError):
        trezor_backend.sign_eth_transaction()
