from nucypher.blockchain.eth.clients import (
    GethClient,
    ParityClient,
    GanacheClient,
    PUBLIC_CHAINS
)
from nucypher.blockchain.eth.interfaces import Blockchain


#
# Mock Providers
#

class MockGethProvider:
    clientVersion = 'Geth/v1.4.11-stable-fed692f6/darwin/go1.7'


class MockParityProvider:
    clientVersion = 'Parity-Ethereum/v2.5.1-beta-e0141f8-20190510/x86_64-linux-gnu/rustc1.34.1'


class MockGanacheProvider:
    clientVersion = 'EthereumJS TestRPC/v2.1.5/ethereum-js'


class ChainIdReporter:
    # Support older and newer versions of web3 py in-test
    version = 5
    chainID = 5


#
# Mock Web3
#

class MockWeb3:

    net = ChainIdReporter

    def __init__(self, provider):
        self.provider = provider

    @property
    def clientVersion(self):
        return self.provider.clientVersion


#
# Mock Blockchain
#

class BlockchainTestBase(Blockchain):

    Web3 = MockWeb3

    def _configure_registry(self, *args, **kwargs):
        pass

    def _setup_solidity(self, *args, **kwargs):
        pass

    def attach_middleware(self):
        pass


class GethClientTestBlockchain(BlockchainTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockGethProvider())

    @property
    def is_local(self):
        return int(self.w3.net.version) not in PUBLIC_CHAINS


class ParityClientTestInterface(BlockchainTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockParityProvider())


class GanacheClientTestInterface(BlockchainTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockGanacheProvider())


def test_geth_web3_client():
    interface = GethClientTestBlockchain(provider_uri='file:///ipc.geth', sync_now=False)
    assert isinstance(interface.client, GethClient)
    assert interface.node_technology == 'Geth'
    assert interface.node_version == 'v1.4.11-stable-fed692f6'
    assert interface.platform == 'darwin'
    assert interface.backend == 'go1.7'

    assert interface.is_local is False
    assert interface.chain_id == 5


def test_parity_web3_client():
    interface = ParityClientTestInterface(provider_uri='file:///ipc.parity', sync_now=False)
    assert isinstance(interface.client, ParityClient)
    assert interface.node_technology == 'Parity-Ethereum'
    assert interface.node_version == 'v2.5.1-beta-e0141f8-20190510'
    assert interface.platform == 'x86_64-linux-gnu'
    assert interface.backend == 'rustc1.34.1'


def test_ganache_web3_client():
    interface = GanacheClientTestInterface(provider_uri='http://ganache:8445', sync_now=False)
    assert isinstance(interface.client, GanacheClient)
    assert interface.node_technology == 'EthereumJS TestRPC'
    assert interface.node_version == 'v2.1.5'
    assert interface.platform is None
    assert interface.backend == 'ethereum-js'
    assert interface.is_local
