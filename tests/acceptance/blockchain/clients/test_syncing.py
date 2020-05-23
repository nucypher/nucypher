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

from nucypher.blockchain.eth.clients import (EthereumClient, GethClient)

# TODO: Relocate mock objects out of unt tests
from tests.unit.test_web3_clients import (
    GethClientTestBlockchain,
    SyncedMockWeb3,
    SyncingMockWeb3,
    SyncingMockWeb3NoPeers
)


def test_synced_geth_client():

    class SyncedBlockchainInterface(GethClientTestBlockchain):

        Web3 = SyncedMockWeb3

    interface = SyncedBlockchainInterface(provider_uri='file:///ipc.geth')
    interface.connect()

    assert interface.client._has_latest_block()
    assert interface.client.sync()


def test_unsynced_geth_client():

    GethClient.SYNC_SLEEP_DURATION = .001

    class NonSyncedBlockchainInterface(GethClientTestBlockchain):

        Web3 = SyncingMockWeb3

    interface = NonSyncedBlockchainInterface(provider_uri='file:///ipc.geth')
    interface.connect()

    assert interface.client._has_latest_block() is False
    assert interface.client.syncing

    assert len(list(interface.client.sync())) == 8


def test_no_peers_unsynced_geth_client():

    GethClient.PEERING_TIMEOUT = .001

    class NonSyncedNoPeersBlockchainInterface(GethClientTestBlockchain):

        Web3 = SyncingMockWeb3NoPeers

    interface = NonSyncedNoPeersBlockchainInterface(provider_uri='file:///ipc.geth')
    interface.connect()

    assert interface.client._has_latest_block() is False
    with pytest.raises(EthereumClient.SyncTimeout):
        list(interface.client.sync())
