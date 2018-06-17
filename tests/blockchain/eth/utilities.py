import random
from typing import List

import pkg_resources
from constant_sorrow import constants
from eth_tester import PyEVMBackend
from eth_tester.backends import is_pyevm_available
from eth_tester.backends.pyevm.main import get_default_genesis_params, get_default_account_keys, generate_genesis_state
from umbral import keys
from web3 import Web3

from nucypher.blockchain.eth.agents import MinerAgent, NucypherTokenAgent
from nucypher.blockchain.eth.deployers import MinerEscrowDeployer, NucypherTokenDeployer


class MockMinerAgent(MinerAgent):
    """MinerAgent with faked config subclass"""

    def spawn_random_miners(self, addresses: list) -> list:
        """
        Deposit and lock a random amount of tokens in the miner escrow
        from each address, "spawning" new Miners.
        """
        from nucypher.blockchain.eth.actors import Miner

        miners = list()
        for address in addresses:
            miner = Miner(miner_agent=self, ether_address=address)
            miners.append(miner)

            # stake a random amount
            min_stake, balance = constants.MIN_ALLOWED_LOCKED, miner.token_balance
            amount = random.randint(min_stake, balance)

            # for a random lock duration
            min_locktime, max_locktime = constants.MIN_LOCKED_PERIODS, constants.MAX_MINTING_PERIODS
            periods = random.randint(min_locktime, max_locktime)

            miner.stake(amount=amount, lock_periods=periods)

        return miners


class MockNucypherTokenDeployer(NucypherTokenDeployer):
    """Mock deployer with mock agency"""
    agency = MockTokenAgent


class MockMinerEscrowDeployer(MinerEscrowDeployer):
    """Helper class for MockMinerAgent, using a mock miner config"""
    agency = MockMinerAgent


class NucypherUmbralPrivateKey(keys.UmbralPrivateKey):

    def export(self, importing_function, *args, **kwargs):
        result = importing_function(private_key=bytes(self.bn_key), *args, **kwargs)
        return result


def generate_accounts(w3: Web3, quantity: int) -> List[str]:
    """
    Generate additional unlocked accounts transferring wei_balance to each account on creation.
    """
    umbral_priv_key = NucypherUmbralPrivateKey.gen_key()
    umbral_pub_key = umbral_priv_key.get_pubkey()

    addresses = list()
    insecure_passphrase = 'this-is-not-a-secure-password'
    for _ in range(quantity):
        address = umbral_priv_key.export(importing_function=w3.personal.importRawKey,
                                         passphrase=insecure_passphrase)

        w3.personal.unlockAccount(address, passphrase=insecure_passphrase)
        addresses.append(addresses)
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

        base_db = get_db_backend()
        genesis_params = get_default_genesis_params()

        # Genesis params overrides
        if overrides is not None:
            genesis_params.update(overrides)

        account_keys = get_default_account_keys()
        genesis_state = generate_genesis_state(account_keys)
        chain = MainnetTesterChain.from_genesis(base_db, genesis_params, genesis_state)

        self.account_keys, self.chain = account_keys, chain


def token_airdrop(token_agent, amount: int, origin: str, addresses: List[str]):
    """Airdrops tokens from creator address to all other addresses!"""

    def txs():
        for address in addresses:
            txhash = token_agent.contract.functions.transfer(address, amount).transact({'from': origin,
                                                                                 'gas': 2000000})
            yield txhash

    receipts = list()
    for tx in txs():    # One at a time
        receipt = token_agent.blockchain.wait_for_receipt(tx)
        receipts.append(receipt)
    return receipts
