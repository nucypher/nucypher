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

from hexbytes import HexBytes
from web3 import Web3

from nucypher.blockchain.eth.signers import TrezorSigner


def test_trezor_transaction_format():
    web3_transaction_dict = {
        'chainId': 1,
        'nonce': 2,
        'gasPrice': 2000000000000,
        'gas': 314159,
        'to': '0xd3CdA913deB6f67967B99D67aCDFa1712C293601',
        'value': 12345,
        'data': b'in that metric, kman is above reproach',
    }

    trezor_transaction = TrezorSigner._format_transaction(web3_transaction_dict)

    assert trezor_transaction['chain_id'] == web3_transaction_dict['chainId']
    assert trezor_transaction['nonce'] == web3_transaction_dict['nonce']
    assert trezor_transaction['gas_price'] == web3_transaction_dict['gasPrice']
    assert trezor_transaction['gas_limit'] == web3_transaction_dict['gas']
    assert trezor_transaction['to'] == web3_transaction_dict['to']
    assert trezor_transaction['value'] == web3_transaction_dict['value']
    assert trezor_transaction['data'] == Web3.toBytes(HexBytes(web3_transaction_dict['data']))
