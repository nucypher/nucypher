import os

import pytest
from cytoolz.dicttoolz import assoc
from eth_account import Account
from eth_account._utils.transactions import Transaction
from eth_utils import to_checksum_address
from hexbytes import HexBytes

from nucypher.blockchain.eth.signers import KeystoreSigner, Signer
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD

# Example keystore filename
MOCK_KEYFILE_NAME = 'UTC--2019-12-04T05-39-04.006429310Z--0xdeadbeef'
MOCK_KEYSTORE_PATH = '/mock-keystore'
MOCK_KEYSTORE_URI = f'keystore://{MOCK_KEYSTORE_PATH}'

TRANSACTION_DICT = {
    "chainId": None,
    "nonce": 0,
    "gasPrice": 1000000000000,
    "gas": 10000,
    "to": "0x13978aee95f38490e9769C39B2773Ed763d9cd5F",
    "value": 10000000000000000,
    "data": ""
}


@pytest.fixture(scope='module', autouse=True)
def mock_listdir(module_mocker):
    mock_listdir = module_mocker.patch.object(os, 'listdir', autospec=True)
    mock_listdir.return_value = [MOCK_KEYFILE_NAME]
    return mock_listdir


@pytest.fixture(scope='module')
def mock_key():
    test_key = Account.create(extra_entropy='M*A*S*H* DIWOKNECNECENOE#@!')
    return test_key


@pytest.fixture(scope='module')
def mock_account(mock_key):
    account = Account.from_key(private_key=mock_key.privateKey)
    return account


@pytest.fixture(scope='function')
def good_signer(mocker, mock_account, mock_key):
    # Return a "real" account address from the keyfile
    mock_keyfile_reader = mocker.patch.object(KeystoreSigner, '_KeystoreSigner__read_keyfile', autospec=True)
    mock_keyfile_reader.return_value = mock_account.address, dict(address=mock_account.address)

    signer = Signer.from_signer_uri(uri=MOCK_KEYSTORE_URI)  # type: KeystoreSigner

    # unlock
    mock_decrypt = mocker.patch.object(Account, 'decrypt', autospec=True)
    mock_decrypt.return_value = mock_key.privateKey
    signer.unlock_account(account=mock_account.address, password=INSECURE_DEVELOPMENT_PASSWORD)

    return signer


@pytest.fixture(scope='module')
def unknown_address():
    address = Account.create().address
    return address


def test_blank_keystore_uri():
    with pytest.raises(Signer.InvalidSignerURI) as error:
        Signer.from_signer_uri(uri='keystore://')  # it's blank!
    assert 'Blank signer URI - No keystore path provided' in str(error)


def test_invalid_keystore(mocker, mock_listdir):
    
    # mock Keystoresigner.__read_keyfile
    # Invalid keystore values and exception handling
    mock_keyfile_reader = mocker.patch.object(KeystoreSigner, '_KeystoreSigner__read_keyfile', autospec=True)
    mock_keyfile_reader.return_value = '0xdeadbeef', dict()

    #
    # 1 - Create
    #

    with pytest.raises(KeystoreSigner.InvalidKeyfile) as e:
        Signer.from_signer_uri(uri=MOCK_KEYSTORE_URI)
    assert "does not contain a valid ethereum address" in str(e.value)

    # Invalid keyfiles
    for exception in (FileNotFoundError, KeyError):
        with pytest.raises(KeystoreSigner.InvalidKeyfile):
            mock_keyfile_reader.side_effect = exception
            Signer.from_signer_uri(uri=MOCK_KEYSTORE_URI)
    mock_keyfile_reader.side_effect = None  # clean up this mess


def test_create_signer(mocker, mock_listdir, mock_account, mock_key):

    # Return a "real" account address from the keyfile
    mock_keyfile_reader = mocker.patch.object(KeystoreSigner, '_KeystoreSigner__read_keyfile', autospec=True)
    mock_keyfile_reader.return_value = mock_account.address, dict(address=mock_account.address)

    signer = Signer.from_signer_uri(uri=MOCK_KEYSTORE_URI)  # type: KeystoreSigner
    assert signer.path == MOCK_KEYSTORE_PATH
    assert len(signer.accounts) == 1
    assert mock_account.address in signer.accounts


def test_keystore_locking(mocker, mock_account, mock_key, good_signer, unknown_address):
    mock_from_key = mocker.patch.object(Account, 'from_key')
    mock_from_key.return_value = mock_account

    #
    # Unlock
    #

    with pytest.raises(Signer.UnknownAccount):
        good_signer.unlock_account(account=unknown_address, password=INSECURE_DEVELOPMENT_PASSWORD)

    successful_unlock = good_signer.unlock_account(account=mock_account.address, password=INSECURE_DEVELOPMENT_PASSWORD)
    assert successful_unlock

    #
    # Lock
    #

    with pytest.raises(Signer.UnknownAccount):
        good_signer.lock_account(account=unknown_address)

    successful_lock = good_signer.lock_account(account=mock_account.address)
    assert successful_lock


def test_list_keystore_accounts(good_signer, mock_account):
    tracked_accounts = good_signer.accounts
    assert mock_account.address in tracked_accounts
    assert len(tracked_accounts) == 1


def test_sign_message(mocker, good_signer, mock_account, mock_key):

    # unlock
    mock_decrypt = mocker.patch.object(Account, 'decrypt', autospec=True)
    mock_decrypt.return_value = mock_key.privateKey
    successful_unlock = good_signer.unlock_account(account=mock_account.address, password=INSECURE_DEVELOPMENT_PASSWORD)
    assert successful_unlock

    # sign message
    message = b'A million tiny bubbles exploding'
    signature = good_signer.sign_message(account=mock_account.address, message=message)
    assert len(signature) == 65


def test_sign_transaction(good_signer, mock_account):
    transaction_dict = assoc(TRANSACTION_DICT, 'from', value=mock_account.address)
    signed_transaction = good_signer.sign_transaction(transaction_dict=transaction_dict)
    assert isinstance(signed_transaction, HexBytes)

    # assert valid transaction
    transaction = Transaction.from_bytes(signed_transaction)
    assert to_checksum_address(transaction.to) == transaction_dict['to']
