import json
import shutil

import pytest
from cytoolz.dicttoolz import assoc
from eth_account import Account
from eth_account._utils.legacy_transactions import Transaction
from eth_utils.address import to_checksum_address, is_checksum_address
from hexbytes.main import HexBytes

from nucypher.blockchain.eth.constants import LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY
from nucypher.blockchain.eth.wallets import Wallet
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD

# Example keystore filename
MOCK_KEYFILE_NAME = 'UTC--2019-12-04T05-39-04.006429310Z--0xdeadbeef'


TRANSACTION_DICT = {
    'chainId': 1,
    'nonce': 2,
    'gasPrice': 2000000000000,
    'gas': 314159,
    'to': '0xd3CdA913deB6f67967B99D67aCDFa1712C293601',
    'value': 12345,
    'data': b'in that metric, kman is above reproach',  # thank you friends
}


@pytest.fixture(scope='module')
def mock_key():
    test_key = Account.create(extra_entropy='M*A*S*H* DIWOKNECNECENOE#@!')
    return test_key


@pytest.fixture(scope='module')
def mock_account(mock_key):
    account = Account.from_key(private_key=mock_key.key)
    return account


@pytest.fixture(scope='module')
def mock_encrypted_key(mock_account):
    encrypted_key = mock_account.encrypt(INSECURE_DEVELOPMENT_PASSWORD)
    return encrypted_key


@pytest.fixture(scope="function")
def wallet(mock_account):
    _wallet = Wallet(account=mock_account)
    return _wallet


@pytest.fixture(scope="function")
def address(wallet):
    _account = wallet.address
    return _account


@pytest.fixture(scope='module')
def mock_keystore(mock_account, tmp_path_factory):
    keystore = tmp_path_factory.mktemp('keystore')
    json.dump(
        mock_account.encrypt(INSECURE_DEVELOPMENT_PASSWORD),
        open(keystore / MOCK_KEYFILE_NAME, 'x+t')
    )
    return keystore


@pytest.fixture(scope='module')
def unknown_address():
    address = Account.create().address
    return address


def test_invalid_keystore(tmp_path):
    with pytest.raises(Wallet.InvalidKeystore) as e:
        Wallet.from_keystore(tmp_path.absolute() / "nonexistent", INSECURE_DEVELOPMENT_PASSWORD)

    empty_path = tmp_path / 'empty_file'
    open(empty_path, 'x+t').close()
    with pytest.raises(Wallet.InvalidKeystore, match=
        'Invalid JSON in keyfile at') as e:
        Wallet.from_keystore(empty_path, INSECURE_DEVELOPMENT_PASSWORD)


def test_signer_reads_keystore_from_disk(mock_account, mock_key, temp_dir_path, mock_encrypted_key):

    # Test reading a keyfile from the disk via KeystoreSigner since
    # it is mocked for the rest of this test module
    fake_ethereum = temp_dir_path / '.fake-ethereum'
    try:
        fake_ethereum.mkdir()

        tmp_keystore = temp_dir_path / '.fake-ethereum' / 'keystore'
        tmp_keystore.mkdir()

        wallet_filepath = tmp_keystore / 'test.json'

        mock_keyfile_path = tmp_keystore / MOCK_KEYFILE_NAME
        mock_keyfile_path.touch(exist_ok=True)

        with open(wallet_filepath, 'w') as fake_keyfile:
            fake_keyfile.write(json.dumps(mock_encrypted_key))

        wallet = Wallet.from_keystore(
            path=wallet_filepath,
            password=INSECURE_DEVELOPMENT_PASSWORD
        )

        assert is_checksum_address(wallet.address)
        assert to_checksum_address(mock_encrypted_key['address']) == wallet.address

    finally:
        if fake_ethereum.exists():
            shutil.rmtree(fake_ethereum, ignore_errors=True)


def test_create_wallet_from_keystore_file(mock_account, mock_keystore):
    mock_keystore_path = mock_keystore / MOCK_KEYFILE_NAME
    signer = Wallet.from_keystore(mock_keystore_path, password=INSECURE_DEVELOPMENT_PASSWORD)
    assert is_checksum_address(signer.address)


def test_wallet_sign_message(mocker, wallet, mock_account, mock_key):

    # unlock
    mock_decrypt = mocker.patch.object(Account, 'decrypt', autospec=True)
    mock_decrypt.return_value = mock_key.key

    # sign message
    message = b'A million tiny bubbles exploding'
    signature = wallet.sign_message(message=message)
    assert len(signature) == LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY


def test_wallet_sign_transaction(wallet, mock_account):
    transaction_dict = assoc(TRANSACTION_DICT, 'from', value=wallet.address)
    signed_transaction = wallet.sign_transaction(transaction_dict=transaction_dict)
    assert isinstance(signed_transaction, HexBytes)

    # assert valid transaction
    transaction = Transaction.from_bytes(signed_transaction)
    assert to_checksum_address(transaction.to) == transaction_dict['to']


def test_memory_wallet_message(wallet, address):
    message = b"An in-memory wallet - because sometimes, having a short-term memory is actually a superpower!"
    signature = wallet.sign_message(message=message)
    assert len(signature) == LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY


def test_memory_wallet_transaction(wallet, address):
    transaction_dict = assoc(TRANSACTION_DICT, "from", value=address)
    signed_transaction = wallet.sign_transaction(transaction_dict=transaction_dict)
    assert isinstance(signed_transaction, HexBytes)
    transaction = Transaction.from_bytes(signed_transaction)
    assert to_checksum_address(transaction.to) == transaction_dict["to"]
