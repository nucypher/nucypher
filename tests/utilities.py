from nkms_eth.blockchain import TheBlockchain
from nkms_eth.deployers import MinerEscrowDeployer, NuCypherKMSTokenDeployer


class TesterBlockchain(TheBlockchain):
    """Transient chain"""
    _network = 'tester'


class MockMinerEscrowDeployer(MinerEscrowDeployer):
    """Speed things up a bit"""
    __hours_per_period = 1
    __min_release_periods = 1


class MockNuCypherKMSTokenDeployer(NuCypherKMSTokenDeployer):

    def _global_airdrop(self, amount: int):
        """Airdrops from creator address to all other addresses!"""

        _creator, *addresses = self._blockchain._chain.web3.eth.accounts

        def txs():
            for address in addresses:
                yield self._contract.transact({'from': self.origin}).transfer(address, amount * (10 ** 6))

        for tx in txs():
            self._blockchain._chain.wait.for_receipt(tx, timeout=10)

        return self
