import pytest
from trezorlib import client as trezor_client
from trezorlib import ethereum as trezor_eth
from trezorlib.messages import EthereumMessageSignature
from trezorlib.transport import TransportException

from nucypher.cli.hardware.backends import Trezor
from nucypher.crypto.signing import InvalidSignature


fake_signature = b"2\xcf?IZ\x9b\x99\x81\xff\xfb\xe2\xf1\x8a\xba\n\xc2\x18\x87nE\xa1\xa2C\xcc\x93+\xef\xe3M0\xed=F\xeaR8,)'\xe9\x83\x92I\x06\xa8\xcdz\xaazn\\\xf9>\xd7h\x1c\x0c\xffC\xdb\x8b\xe5\xa4V\x1c"
fake_address = '0xE67d36f4063eEd7a3464D243752669b6503883f8'
fake_message = b'test'


@pytest.fixture()
def mock_trezorlib(mocker):

    trezor_client.get_default_client = lambda: None

    def mocked_sign_message(client, bip44_path, message):

        return EthereumMessageSignature(
                signature=fake_signature,
                address=fake_address)

    def mocked_verify_message(client, address, signature, message):
        if (address != fake_address or signature != fake_signature or
                message != fake_message):
            return False
        return True

    mock_load = {
            'sign_message': mocked_sign_message,
            'verify_message': mocked_verify_message,
    }

    for method, patch in mock_load.items():
        mocker.patch.object(trezor_eth, method, patch)


def test_trezor_defaults(mock_trezorlib, mocker):
    trezor_backend = Trezor()

    assert trezor_backend.DEFAULT_BIP44_PATH == "m/44'/60'/0'/0"
    assert trezor_backend._Trezor__bip44_path == [2147483692, 2147483708, 2147483648, 0]

    def fail_get_default_client():
        raise TransportException("No device found...")

    trezor_client.get_default_client = fail_get_default_client
    with pytest.raises(RuntimeError):
        Trezor()
    trezor_client.get_default_client = lambda: None


def test_trezor_sign_and_verify(mock_trezorlib):
    trezor_backend = Trezor()

    test_sig = trezor_backend.sign_message(b'test')
    assert hasattr(test_sig, 'signature')
    assert hasattr(test_sig, 'address')

    assert trezor_backend.verify_message(test_sig.signature, b'test',
                                         test_sig.address)

    with pytest.raises(InvalidSignature):
        trezor_backend.verify_message(test_sig.signature, b'bad message',
                                      test_sig.address)
