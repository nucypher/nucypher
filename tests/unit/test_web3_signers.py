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


import pytest
from eth_account import Account
from eth_account._utils.legacy_transactions import Transaction
from eth_account.account import Account
from eth_utils.address import to_checksum_address
from hexbytes import HexBytes
from toolz.dicttoolz import assoc
from trezorlib.messages import EthereumGetAddress

from nucypher.blockchain.eth import signers
from nucypher.blockchain.eth.signers import Signer
from nucypher.blockchain.eth.signers import TrezorSigner

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
def mock_account():
    key = Account.create(extra_entropy='M*A*S*H* DIWOKNECNECENOE#@!')
    account = Account.from_key(private_key=key.key)
    return account


@pytest.fixture(scope='module')
def simple_trezor_uri():
    return TrezorSigner.uri_scheme()


def test_blank_keystore_uri():
    with pytest.raises(Signer.InvalidSignerURI, match='Blank signer URI - No keystore path provided') as error:
        Signer.from_signer_uri(uri='keystore://', testnet=True)  # it's blank!


def test_trezor_transaction_format():
    trezor_transaction = TrezorSigner._format_transaction(TRANSACTION_DICT)
    assert trezor_transaction['chain_id'] == TRANSACTION_DICT['chainId']
    assert trezor_transaction['nonce'] == TRANSACTION_DICT['nonce']
    assert trezor_transaction['gas_price'] == TRANSACTION_DICT['gasPrice']
    assert trezor_transaction['gas_limit'] == TRANSACTION_DICT['gas']
    assert trezor_transaction['to'] == TRANSACTION_DICT['to']
    assert trezor_transaction['value'] == TRANSACTION_DICT['value']


@pytest.fixture(scope='function')
def mock_trezor(mocker, mock_account):
    class FakeTrezorClient:

        # fake out
        v = 38
        r = b"!\xab\x18\xb2\x9e\xa0\xe6\xa7$\x11\x8fA`\x15\xe1\xad\x1dt\xefL\xc5\\\xec:\x88'\xa7\xe3\xcb\xb6\xfc\xb3"
        s = b"\xc4\xc2O\xda\x06o\x83\x03r\x9e[K\xc1\xcd\xd8\x12\xbc.l\xbb\x8cdl\xaf\xba=p\xeco\xe9\x9e\x89"
        faked_vrs = v, r, s

        def call(self, message):
            if isinstance(message, EthereumGetAddress):
                return mock_account.address

        def get_device_id(self, *args, **kwargs):
            return '1'  # look at me im a trezor device id! :-p

        def get_address(self, *args, **kwargs):
            return mock_account.address

    mocker.patch.object(signers.hardware, 'get_default_client', return_value=FakeTrezorClient())
    mocker.patch.object(TrezorSigner, '_open')
    mocker.patch.object(TrezorSigner, '_TrezorSigner__derive_account', return_value=mock_account.address)
    mocker.patch.object(TrezorSigner, '_TrezorSigner__sign_transaction', return_value=FakeTrezorClient.faked_vrs)


def test_trezor_signer_creation_from_uri(mock_trezor, simple_trezor_uri):
    signer = Signer.from_signer_uri(uri=simple_trezor_uri, testnet=False)
    assert isinstance(signer, TrezorSigner)
    assert len(signer.accounts) == 1
    del signer


def test_trezor_signer_uri_slip44_paths(mock_trezor, simple_trezor_uri):

    # default
    signer = TrezorSigner.from_signer_uri(uri=simple_trezor_uri)
    assert signer.derivation_root == "44'/60'/0'/0"
    del signer

    # explicit mainnet
    signer = TrezorSigner.from_signer_uri(uri=simple_trezor_uri, testnet=False)
    assert signer.derivation_root == "44'/60'/0'/0"

    # explicit testnet
    signer = TrezorSigner.from_signer_uri(uri=simple_trezor_uri, testnet=True)
    assert signer.derivation_root == "44'/1'/0'/0"  # SLIP44 testnet path
    assert len(signer.accounts) == 1
    del signer


# def test_trezor_signer_rich_uri(mock_trezor, simple_trezor_uri):
    # TODO: #2269 Support "rich URIs" for trezors
    # simple = simple_trezor_uri
    # prefix_only = 'trezor://'
    # uri_with_device_id = "trezor://1209:53c1:01"
    # uri_with_device_id_and_path = "trezor://1209:53c1:01/m/44'/60'/0'/0/0"
    # uri_with_path = "trezor:///m/44'/60'/0'/0/0"
    # uri_with_checksum_address = "trezor://0xdeadbeef"
    # trezor_signer = TrezorSigner.from_signer_uri()


def test_trezor_sign_transaction(mock_trezor, mock_account):
    trezor_signer = TrezorSigner()
    transaction_dict = assoc(TRANSACTION_DICT, key='from', value=mock_account.address)
    signed_transaction = trezor_signer.sign_transaction(transaction_dict=transaction_dict)
    assert isinstance(signed_transaction, HexBytes)

    # assert valid deserializable transaction
    transaction = Transaction.from_bytes(signed_transaction)

    # Confirm the integrity of the sender and recipient address
    failure_message = 'WARNING: transaction "to" field was mutated'
    sender_checksum_address = to_checksum_address(transaction.to)
    assert sender_checksum_address != mock_account.address, failure_message
    assert sender_checksum_address == TRANSACTION_DICT['to'], failure_message
    assert sender_checksum_address == transaction_dict['to']  # positive
    assert sender_checksum_address != mock_account.address    # negative
