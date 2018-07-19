import os
import random

from constant_sorrow import constants
from twisted.internet import protocol

from nucypher.blockchain.eth.chains import TesterBlockchain
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer, MinerEscrowDeployer, PolicyManagerDeployer
from tests.blockchain.eth.utilities import token_airdrop


def __bootstrap_network() -> tuple:

    # Connect to the blockchain
    blockchain = TesterBlockchain.from_config()

    # Parse addresses
    etherbase, alice, bob, *ursulas = blockchain.interface.w3.eth.accounts
    origin, *everybody_else = blockchain.interface.w3.eth.accounts

    # Deploy contracts
    token_deployer = NucypherTokenDeployer(blockchain=blockchain, deployer_address=origin)
    token_deployer.arm()
    token_deployer.deploy()
    token_agent = token_deployer.make_agent()

    miner_escrow_deployer = MinerEscrowDeployer(token_agent=token_agent, deployer_address=origin)
    miner_escrow_deployer.arm()
    miner_escrow_deployer.deploy()
    miner_agent = miner_escrow_deployer.make_agent()

    policy_manager_deployer = PolicyManagerDeployer(miner_agent=miner_agent, deployer_address=origin)
    policy_manager_deployer.arm()
    policy_manager_deployer.deploy()
    _policy_agent = policy_manager_deployer.make_agent()

    # Airdrop ethereum
    airdrop_amount = 1000000 * int(constants.M)
    _receipts = token_airdrop(token_agent=token_agent,
                              origin=etherbase,
                              addresses=ursulas,
                              amount=airdrop_amount)

    return token_agent, miner_agent, _policy_agent


class UrsulaProcessProtocol(protocol.ProcessProtocol):
    def __init__(self):
        pass

    def connectionMade(self):
        pass

    def processExited(self, reason):
        os.remove(self.ursula.db_name)

    def outReceived(self, data):
        print(data)

    def errReceived(self, data):
        print(data)

    def noResponse(self, err):
        self.transport.loseConnection()


class SimulatedUrsulaProcessProtocol(UrsulaProcessProtocol):
    """Subclass of UrsulaProcessProtocol"""

    def simulate_staking(self):
        print("Starting {}".format(self))

        # Choose random valid stake amount
        min_stake, balance = int(constants.MIN_ALLOWED_LOCKED), self.ursula.token_balance
        amount = random.randint(min_stake, balance)

        # fChoose random valid stake duration in periods
        min_locktime, max_locktime = int(constants.MIN_LOCKED_PERIODS), int(constants.MAX_MINTING_PERIODS)
        periods = random.randint(min_locktime, max_locktime)

        # Stake
        self.ursula.stake(amount=amount, lock_periods=periods)
