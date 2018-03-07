from nkms_eth.blockchain import TheBlockchain
from nkms_eth.escrow import MinerAgent


class TesterBlockchain(TheBlockchain):
    """Transient chain"""
    __network = 'tester'


class MockMinerEscrow(MinerAgent):
    """Speed things up a bit"""
    __hours_per_period = 1
    __min_release_periods = 1
