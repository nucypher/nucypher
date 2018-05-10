import random
from typing import List

import pkg_resources
from eth_tester import PyEVMBackend
from eth_tester.backends import is_pyevm_available
from eth_tester.backends.pyevm.main import get_default_genesis_params, get_default_account_keys, generate_genesis_state
from web3 import Web3

from nucypher.blockchain.eth.agents import MinerAgent, NuCypherTokenAgent
from nucypher.blockchain.eth.constants import NuCypherMinerConfig
from nucypher.blockchain.eth.deployers import MinerEscrowDeployer, NuCypherTokenDeployer


class MockNuCypherMinerConfig(NuCypherMinerConfig):
    """Speed things up a bit"""
    # _hours_per_period = 24     # Hours
    # min_locked_periods = 1     # Minimum locked periods


class MockTokenAgent(NuCypherTokenAgent):

    def token_airdrop(self, amount: int, addresses: List[str]=None):
        """Airdrops tokens from creator address to all other addresses!"""

        if addresses is None:
            _creator, *addresses = self.blockchain.provider.w3.eth.accounts

        def txs():
            for address in addresses:
                txhash = self.contract.functions.transfer(address, amount).transact({'from': self.origin})
                yield txhash

        receipts = list()
        for tx in txs():    # One at a time
            receipt = self.blockchain.wait_for_receipt(tx)
            receipts.append(receipt)
        return receipts


class MockMinerAgent(MinerAgent, MockNuCypherMinerConfig):
    """MinerAgent with faked config subclass"""

    def spawn_random_miners(self, addresses: list) -> list:
        """
        Deposit and lock a random amount of tokens in the miner escrow
        from each address, "spawning" new Miners.
        """
        from nucypher.blockchain.eth.actors import Miner

        miners = list()
        for address in addresses:
            miner = Miner(miner_agent=self, address=address)
            miners.append(miner)

            # stake a random amount
            min_stake, balance = self.min_allowed_locked, miner.token_balance()
            amount = random.randint(min_stake, balance)

            # for a random lock duration
            min_locktime, max_locktime = self.min_locked_periods, self.max_minting_periods
            periods = random.randint(min_locktime, max_locktime)

            miner.stake(amount=amount, periods=periods)

        return miners


class MockNuCypherTokenDeployer(NuCypherTokenDeployer):
    """Mock deployer with mock agency"""
    agency = MockTokenAgent


class MockMinerEscrowDeployer(MinerEscrowDeployer, MockNuCypherMinerConfig):
    """Helper class for MockMinerAgent, using a mock miner config"""
    agency = MockMinerAgent


def generate_accounts(w3: Web3, quantity: int) -> List[str]:
    """
    Generate 9 additional unlocked accounts transferring wei_balance to each account on creation.
    """
    addresses = list()
    insecure_passphrase = 'this-is-not-a-secure-password'
    for _ in range(quantity):
        address = w3.personal.newAccount(insecure_passphrase)
        w3.personal.unlockAccount(address, passphrase=insecure_passphrase)

        addresses.append(addresses)

    accounts = len(w3.eth.accounts)
    fail_message = "There are more total accounts then the specified quantity; There are {} existing accounts.".format(accounts)
    assert accounts == 10, fail_message

    return addresses


class TesterPyEVMBackend(PyEVMBackend):

    def __init__(self, genesis_overrides=None):
        """
        Example overrides
        ---------------------------------
        coinbase: address_bytes
        difficulty: int(default: 131072)
        extra_data: bytes
        gas_limit: int(default: 3141592)
        gas_used: int(default: 0)
        nonce: bytes
        block_number: int
        timestamp: int(epoch)
        """

        self.fork_config = dict()

        if not is_pyevm_available():
            raise pkg_resources.DistributionNotFound(
                "The `py-evm` package is not available.  The "
                "`PyEVMBackend` requires py-evm to be installed and importable. "
                "Please install the `py-evm` library."
            )

        self.reset_to_genesis(overrides=genesis_overrides)

    def reset_to_genesis(self, overrides=None):
        from evm.chains.tester import MainnetTesterChain
        from evm.db import get_db_backend
        from evm.db.chain import ChainDB

        db = ChainDB(get_db_backend())
        genesis_params = get_default_genesis_params()

        # Genesis params overrides
        if overrides is not None:
            genesis_params.update(overrides)

        account_keys = get_default_account_keys()
        genesis_state = generate_genesis_state(account_keys)
        chain = MainnetTesterChain.from_genesis(db, genesis_params, genesis_state)

        self.account_keys, self.chain = account_keys, chain
