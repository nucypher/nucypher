import pytest
from cytoolz import assoc
from eth_account._utils.legacy_transactions import Transaction
from eth_utils import to_checksum_address
from hexbytes import HexBytes

from nucypher.blockchain.eth.constants import LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY
from nucypher.blockchain.eth.signers import InMemorySigner, Signer
from tests.unit.test_web3_signers import TRANSACTION_DICT


@pytest.fixture(scope="function")
def signer():
    _signer = InMemorySigner()
    return _signer


@pytest.fixture(scope="function")
def account(signer):
    _account = signer.accounts[0]
    return _account


def test_memory_signer_from_signer_uri():
    signer = Signer.from_signer_uri(uri="memory://")
    assert isinstance(signer, InMemorySigner)


def test_memory_signer_uri_scheme(signer):
    assert signer.uri_scheme() == "memory"


def test_memory_signer_accounts(signer):
    assert len(signer.accounts) == 1
    assert isinstance(signer.accounts[0], str)
    assert len(signer.accounts[0]) == 42


def test_memory_signer_lock_account(signer, account):
    assert signer.is_device(account=account) is False
    assert signer.lock_account(account=account) is True
    assert signer.is_device(account=account) is False
    assert signer.unlock_account(account=account, password="password") is True


def test_memory_signer_message(signer, account):
    message = b"An in-memory signer - because sometimes, having a short-term memory is actually a superpower!"
    signature = signer.sign_message(account=account, message=message)
    assert len(signature) == LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY


def test_memory_signer_transaction(signer, account):
    transaction_dict = assoc(TRANSACTION_DICT, "from", value=account)
    signed_transaction = signer.sign_transaction(transaction_dict=transaction_dict)
    assert isinstance(signed_transaction, HexBytes)
    transaction = Transaction.from_bytes(signed_transaction)
    assert to_checksum_address(transaction.to) == transaction_dict["to"]
