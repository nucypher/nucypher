import random

from nkms_eth.actors import Miner
from nkms_eth.agents import MinerAgent, EthereumContractAgent
from nkms_eth.blockchain import TheBlockchain
from nkms_eth.config import NuCypherMinerConfig
from nkms_eth.deployers import MinerEscrowDeployer, NuCypherKMSTokenDeployer


class TesterBlockchain(TheBlockchain):
    """Transient, in-memory, local, private chain"""

    _network = 'tester'

    def wait_time(self, wait_hours, step=50):
        """Wait the specified number of wait_hours by comparing block timestamps."""

        end_timestamp = self._chain.web3.eth.getBlock(
            self._chain.web3.eth.blockNumber).timestamp + wait_hours * 60 * 60
        while self._chain.web3.eth.getBlock(self._chain.web3.eth.blockNumber).timestamp < end_timestamp:
            self._chain.wait.for_block(self._chain.web3.eth.blockNumber + step)

    def spawn_miners(self, miner_agent: MinerAgent, addresses: list, locktime: int, m: int) -> None:
        """
        Deposit and lock a random amount of tokens in the miner escrow
        from each address, "spawning" new Miners.
        """
        for address in addresses:
            miner = Miner(miner_agent=miner_agent, address=address)
            amount = miner.token_balance() // 2

            # amount = (10 + random.randrange(9000)) * m
            miner.stake(amount=amount, locktime=locktime, auto_switch_lock=True)


class MockNuCypherKMSTokenDeployer(NuCypherKMSTokenDeployer):
    _M = 10 ** 6    #TODO: Unify with config class's _M

    def _global_airdrop(self, amount: int):
        """Airdrops from creator address to all other addresses!"""

        _creator, *addresses = self.blockchain._chain.web3.eth.accounts

        def txs():
            for address in addresses:
                txhash = self._contract.transact({'from': self._creator}).transfer(address, amount)
                yield txhash

        receipts = []
        for tx in txs():    # One at a time
            receipt = self.blockchain.wait_for_receipt(tx)
            receipts.append(receipt)
        return receipts


class MockNuCypherMinerConfig(NuCypherMinerConfig):
    """Speed things up a bit"""
    _hours_per_period = 1     # Hours
    _min_release_periods = 1  # Minimum switchlock periods


class MockMinerEscrowDeployer(MinerEscrowDeployer, MockNuCypherMinerConfig):
    """Helper class for MockMinerAgent"""


class MockMinerAgent(MinerAgent):
    """MinerAgent with faked config subclass"""
    _deployer = MockMinerEscrowDeployer
