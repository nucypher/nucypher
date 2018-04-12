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
