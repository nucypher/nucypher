import json
import shutil

import pytest
from cytoolz.dicttoolz import assoc
from eth_account._utils.legacy_transactions import Transaction
from eth_account.account import Account as EthAccount
from eth_utils.address import is_checksum_address, to_checksum_address
from hexbytes.main import HexBytes

from nucypher.blockchain.eth.accounts import LocalAccount
from nucypher.blockchain.eth.constants import LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD
from tests.utils.blockchain import TestAccount

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
def wallet():
    account = TestAccount.random()
    return account


@pytest.fixture(scope="function")
def address(wallet):
    _account = wallet.address
    return _account


@pytest.fixture(scope='module')
def mock_keystore(wallet, tmp_path_factory):
    keystore = tmp_path_factory.mktemp('keystore')
    filepath = keystore / MOCK_KEYFILE_NAME
    wallet.to_keystore(path=filepath, password=INSECURE_DEVELOPMENT_PASSWORD)
    return filepath


def test_invalid_keystore(tmp_path, capture_wallets):
    with pytest.raises(FileNotFoundError):
        LocalAccount.from_keystore(tmp_path.absolute() / "nonexistent", INSECURE_DEVELOPMENT_PASSWORD)

    # simulate a file with invalid JSON
    empty_path = tmp_path / 'empty_file'
    capture_wallets[empty_path] = ''

    with pytest.raises(
        LocalAccount.InvalidKeystore, match="Invalid JSON in wallet keystore at"
    ):
        LocalAccount.from_keystore(empty_path, INSECURE_DEVELOPMENT_PASSWORD)


def test_signer_reads_keystore_from_disk(temp_dir_path, capture_wallets):

    mock_encrypted_key = EthAccount.create().encrypt(INSECURE_DEVELOPMENT_PASSWORD)

    # Test reading a keyfile from the disk via KeystoreSigner since
    # it is mocked for the rest of this test module
    fake_ethereum = temp_dir_path / '.fake-ethereum'
    try:
        fake_ethereum.mkdir()

        tmp_keystore = temp_dir_path / '.fake-ethereum' / 'keystore'
        tmp_keystore.mkdir()

        wallet_filepath = tmp_keystore / 'test.json'

        # this is a filesystem write
        capture_wallets[wallet_filepath] = json.dumps(mock_encrypted_key)

        wallet = LocalAccount.from_keystore(
            path=wallet_filepath,
            password=INSECURE_DEVELOPMENT_PASSWORD
        )

        assert is_checksum_address(wallet.address)
        assert to_checksum_address(mock_encrypted_key['address']) == wallet.address

    finally:
        if fake_ethereum.exists():
            shutil.rmtree(fake_ethereum, ignore_errors=True)


def test_create_wallet_from_keystore_file(mock_keystore):
    mock_keystore_filepath = mock_keystore
    signer = LocalAccount.from_keystore(mock_keystore_filepath, password=INSECURE_DEVELOPMENT_PASSWORD)
    assert is_checksum_address(signer.address)


def test_wallet_sign_message(mocker, wallet):
    message = b'A million tiny bubbles exploding'
    signature = wallet.sign_message(message=message)
    assert len(signature) == LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY


def test_wallet_sign_transaction(wallet):
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
