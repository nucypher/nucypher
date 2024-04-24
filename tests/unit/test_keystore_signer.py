import json

import pytest
from cytoolz import assoc
from eth_account._utils.legacy_transactions import Transaction
from eth_account.messages import encode_defunct
from eth_utils import to_checksum_address
from hexbytes import HexBytes

from nucypher.blockchain.eth.constants import LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY
from nucypher.blockchain.eth.signers import KeystoreSigner, Signer

PASSWORD = "so_secure"


@pytest.fixture(scope="module")
def keystore_file(random_account, temp_dir_path):
    _keystore_file = temp_dir_path / "keystore_file.json"
    with _keystore_file.open("w") as f:
        key_data = random_account.encrypt(PASSWORD)
        json.dump(key_data, f)
    yield _keystore_file


@pytest.fixture(scope="module")
def signer(keystore_file):
    signer = Signer.from_signer_uri(uri=f"keystore://{keystore_file.absolute()}")
    yield signer


def test_blank_keystore_uri():
    with pytest.raises(
        Signer.InvalidSignerURI, match="Blank signer URI - No keystore path provided"
    ):
        Signer.from_signer_uri(uri="keystore://", testnet=True)  # it's blank!


def test_keystore_signer_from_signer_uri(random_account, signer):
    assert isinstance(signer, KeystoreSigner)
    assert signer.uri_scheme() == "keystore"

    assert len(signer.accounts) == 1
    assert isinstance(signer.accounts[0], str)
    assert signer.accounts[0] == random_account.address
    assert len(signer.accounts[0]) == 42


def test_keystore_signer_lock_account(signer, random_account):
    account = random_account.address
    assert signer.is_device(account=account) is False
    assert signer.lock_account(account=account) is True
    assert signer.is_device(account=account) is False
    assert signer.unlock_account(account=account, password=PASSWORD) is True


def test_keystore_signer_message(signer, random_account):
    message = b"Our attitude toward life determines life's attitude towards us."  # - Earl Nightingale
    signature = signer.sign_message(account=random_account.address, message=message)
    assert len(signature) == LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY

    assert (
        signature
        == random_account.sign_message(encode_defunct(primitive=message)).signature
    )


def test_keystore_signer_transaction(signer, random_account, tx_dict):
    transaction_dict = assoc(tx_dict, "from", value=random_account.address)
    signed_transaction = signer.sign_transaction(transaction_dict=transaction_dict)
    assert isinstance(signed_transaction, HexBytes)
    assert (
        signed_transaction
        == random_account.sign_transaction(transaction_dict).rawTransaction
    )

    transaction = Transaction.from_bytes(signed_transaction)
    assert to_checksum_address(transaction.to) == transaction_dict["to"]
