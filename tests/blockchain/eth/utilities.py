from typing import List

import pkg_resources
from eth_tester import PyEVMBackend
from eth_tester.backends import is_pyevm_available
from eth_tester.backends.pyevm.main import get_default_genesis_params, get_default_account_keys, generate_genesis_state
from web3 import Web3

from nkms.blockchain.eth.agents import MinerAgent
from nkms.blockchain.eth.constants import NuCypherMinerConfig
from nkms.blockchain.eth.deployers import MinerEscrowDeployer


class MockNuCypherMinerConfig(NuCypherMinerConfig):
    """Speed things up a bit"""
    _hours_per_period = 1     # Hours
    _min_release_periods = 1  # Minimum switchlock periods


class MockMinerEscrowDeployer(MinerEscrowDeployer, MockNuCypherMinerConfig):
    """Helper class for MockMinerAgent, using a mock miner config"""


class MockMinerAgent(MinerAgent):
    """MinerAgent with faked config subclass"""
    _deployer = MockMinerEscrowDeployer


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

        self.fork_config = {}

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
