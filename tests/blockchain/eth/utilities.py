import random
from typing import List

from constant_sorrow import constants
from umbral import keys
from web3 import Web3

from nucypher.blockchain.eth.agents import MinerAgent
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
