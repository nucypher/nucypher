from nkms_eth.blockchain import Blockchain
from nkms_eth.escrow import Escrow


class TesterBlockchain(Blockchain):
    """Transient chain"""
    _network = 'tester'


class MockEscrow(Escrow):
    """Speed things up a bit"""
    hours_per_period = 1
    min_release_periods = 1
