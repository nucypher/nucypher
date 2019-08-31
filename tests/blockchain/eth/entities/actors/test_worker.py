import pytest
import pytest_twisted
from twisted.internet import threads
from twisted.internet.task import Clock

from nucypher.blockchain.eth.token import NU, PeriodTracker
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD
from nucypher.utilities.sandbox.ursula import make_decentralized_ursulas, start_pytest_ursula_services


@pytest.mark.slow()
@pytest_twisted.inlineCallbacks
def test_worker_auto_confirmations(testerchain,
                                   test_registry,
                                   staker,
                                   agency,
                                   token_economics,
                                   ursula_decentralized_test_config):

    # Mock Powerup consumption (Ursula-Worker)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=staker.checksum_address)
    testerchain.transacting_power.activate()

    staker.initialize_stake(amount=NU(token_economics.minimum_allowed_locked, 'NuNit'),
                            lock_periods=int(token_economics.minimum_locked_periods))

    # Get an unused address and create a new worker
    worker_address = testerchain.unassigned_accounts[-1]

    # Control time
    clock = Clock()
    PeriodTracker.CLOCK = clock

    ursula = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                        stakers_addresses=[staker.checksum_address],
                                        workers_addresses=[worker_address],
                                        confirm_activity=False,
                                        registry=test_registry).pop()

    # Bond the Worker and Staker
    staker.set_worker(worker_address=worker_address)

    # Start running the worker
    def start():
        start_pytest_ursula_services(ursula=ursula)
        ursula.period_tracker.start()

    def time_travel(_):
        testerchain.time_travel(periods=2)
        two_hours = (60*60) * 2
        clock.advance(two_hours)

    def verify(_):
        # Verify that periods were confirmed on-chain automatically
        last_active_period = staker.staking_agent.get_last_active_period(address=staker.checksum_address)
        current_period = staker.staking_agent.get_current_period()
        assert (last_active_period - current_period) == 1

    # Run the callbacks
    d = threads.deferToThread(start)
    for i in range(5):
        d.addCallback(time_travel)
        d.addCallback(verify)
    yield d
