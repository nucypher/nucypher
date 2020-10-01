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

from nucypher.blockchain.eth.clients import EthereumClient


@pytest.fixture(scope='function', autouse=True)
def monkeypatch_confirmations(testerchain, monkeypatch):
    def block_until_enough_confirmations(ethclient: EthereumClient, transaction_hash, *args, **kwargs):
        ethclient.log.debug(f'Confirmations mocked - instantly confirmed {kwargs.get("confirmations")} blocks!')
        return testerchain.wait_for_receipt(txhash=transaction_hash)
    monkeypatch.setattr(EthereumClient, 'block_until_enough_confirmations', block_until_enough_confirmations)
