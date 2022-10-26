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
from eth_account.account import Account

from nucypher.blockchain.eth.signers import Signer

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


def test_blank_keystore_uri():
    with pytest.raises(Signer.InvalidSignerURI, match='Blank signer URI - No keystore path provided') as error:
        Signer.from_signer_uri(uri='keystore://', testnet=True)  # it's blank!
