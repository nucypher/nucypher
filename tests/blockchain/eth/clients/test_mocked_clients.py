import datetime
import pytest

from nucypher.blockchain.eth.clients import (
    Web3Client,
    GethClient,
    ParityClient,
    GanacheClient,
    PUBLIC_CHAINS
)
from nucypher.blockchain.eth.interfaces import BlockchainInterface


#
# Mock Providers
#

class MockGethProvider:
    clientVersion = 'Geth/v1.4.11-stable-fed692f6/darwin/go1.7'


class MockParityProvider:
    clientVersion = 'Parity-Ethereum/v2.5.1-beta-e0141f8-20190510/x86_64-linux-gnu/rustc1.34.1'


class MockGanacheProvider:
    clientVersion = 'EthereumJS TestRPC/v2.1.5/ethereum-js'


class SyncedMockW3Eth:

    # Support older and newer versions of web3 py in-test
    version = 5
    chainId = hex(5)
    blockNumber = 5

    def getBlock(self, blockNumber):
        return {
            'timestamp': datetime.datetime.timestamp(datetime.datetime.now() - datetime.timedelta(seconds=25))
        }


class SyncingMockW3Eth(SyncedMockW3Eth):

    _sync_test_limit = 3

    def __init__(self, *args, **kwargs):
        self._syncing_counter = 0

        super().__init__(*args, **kwargs)

    @property
    def syncing(self):

        if self._syncing_counter < self._sync_test_limit:
            self._syncing_counter += 1
            return {
                'currentBlock': self._syncing_counter,
                'highestBlock': self._sync_test_limit,
            }


        return False


    def getBlock(self, blockNumber):
        return {
            'timestamp': datetime.datetime.timestamp(datetime.datetime.now() - datetime.timedelta(seconds=500))
        }


class MockedW3GethWithPeers:

    @property
    def admin(self):

        class GethAdmin:

            def peers(self):
                return [1, 2, 3]

        return GethAdmin()


class MockedW3GethWithNoPeers:

    @property
    def admin(self):

        class GethAdmin:

            def peers(self):
                return []

        return GethAdmin()


#
# Mock Web3
#

class SyncedMockWeb3:

    net = SyncedMockW3Eth()
    eth = SyncedMockW3Eth()
    geth = MockedW3GethWithPeers()

    def __init__(self, provider):
        self.provider = provider

    @property
    def clientVersion(self):
        return self.provider.clientVersion

    @property
    def isConnected(self):
        return lambda: True


class SyncingMockWeb3(SyncedMockWeb3):

    net = SyncingMockW3Eth()
    eth = SyncingMockW3Eth()


class SyncingMockWeb3NoPeers(SyncingMockWeb3):

    geth = MockedW3GethWithNoPeers()


# Mock Blockchain
#

class BlockchainInterfaceTestBase(BlockchainInterface):

    Web3 = SyncedMockWeb3

    def _configure_registry(self, *args, **kwargs):
        pass

    def _setup_solidity(self, *args, **kwargs):
        pass

    def attach_middleware(self):
        pass


class GethClientTestBlockchain(BlockchainInterfaceTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockGethProvider())

    @property
    def is_local(self):
        return int(self.w3.net.version) not in PUBLIC_CHAINS


class ParityClientTestInterface(BlockchainInterfaceTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockParityProvider())


class GanacheClientTestInterface(BlockchainInterfaceTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockGanacheProvider())


def test_geth_web3_client():
    interface = GethClientTestBlockchain(provider_uri='file:///ipc.geth')
    interface.connect(fetch_registry=False, sync_now=False)

    assert isinstance(interface.client, GethClient)
    assert interface.client.node_technology == 'Geth'
    assert interface.client.node_version == 'v1.4.11-stable-fed692f6'
    assert interface.client.platform == 'darwin'
    assert interface.client.backend == 'go1.7'

    assert interface.client.is_local is False
    assert interface.client.chain_id == '5'  # Hardcoded above


def test_parity_web3_client():
    interface = ParityClientTestInterface(provider_uri='file:///ipc.parity')
    interface.connect(fetch_registry=False, sync_now=False)

    assert isinstance(interface.client, ParityClient)
    assert interface.client.node_technology == 'Parity-Ethereum'
    assert interface.client.node_version == 'v2.5.1-beta-e0141f8-20190510'
    assert interface.client.platform == 'x86_64-linux-gnu'
    assert interface.client.backend == 'rustc1.34.1'


def test_ganache_web3_client():
    interface = GanacheClientTestInterface(provider_uri='http://ganache:8445')
    interface.connect(fetch_registry=False, sync_now=False)

    assert isinstance(interface.client, GanacheClient)
    assert interface.client.node_technology == 'EthereumJS TestRPC'
    assert interface.client.node_version == 'v2.1.5'
    assert interface.client.platform is None
    assert interface.client.backend == 'ethereum-js'
    assert interface.client.is_local


def test_datetime_logic():

    # test for https://github.com/nucypher/nucypher/pull/1203/files/29c0152f404cc8e46b80feb12a1440f5360ddbff#r311679487

    delta = (
        datetime.datetime.now() -
        datetime.datetime.fromtimestamp(
            datetime.datetime.timestamp(datetime.datetime.now() - datetime.timedelta(seconds=603))
        )
    )

    assert isinstance(delta, datetime.timedelta)
    assert delta.seconds == 602


def test_synced_geth_client():

    class SyncedBlockchainInterface(GethClientTestBlockchain):

        Web3 = SyncedMockWeb3

    interface = SyncedBlockchainInterface(provider_uri='file:///ipc.geth')
    interface.connect(fetch_registry=False, sync_now=False)

    assert interface.client._has_latest_block()
    assert interface.client.sync()


def test_unsynced_geth_client():

    GethClient.SYNC_TIMEOUT_DURATION = 2

    class NonSyncedBlockchainInterface(GethClientTestBlockchain):

        Web3 = SyncingMockWeb3

    interface = NonSyncedBlockchainInterface(provider_uri='file:///ipc.geth')
    interface.connect(fetch_registry=False, sync_now=False)

    assert interface.client._has_latest_block() is False
    assert interface.client.syncing

    with pytest.raises(Web3Client.SyncTimeout):
        assert interface.client.sync()


def test_no_peers_unsynced_geth_client():

    GethClient.SYNC_TIMEOUT_DURATION = 2

    class NonSyncedNoPeersBlockchainInterface(GethClientTestBlockchain):

        Web3 = SyncingMockWeb3NoPeers

    interface = NonSyncedNoPeersBlockchainInterface(provider_uri='file:///ipc.geth')
    interface.connect(fetch_registry=False, sync_now=False)

    assert interface.client._has_latest_block() is False
    with pytest.raises(Web3Client.SyncTimeout):
        assert interface.client.sync()
