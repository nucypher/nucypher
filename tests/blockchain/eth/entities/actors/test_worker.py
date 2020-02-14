import pytest
import pytest_twisted
from twisted.internet import threads
from twisted.internet.task import Clock

from nucypher.blockchain.eth.actors import Worker
from nucypher.blockchain.eth.token import NU, WorkTracker
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
                                   mock_transacting_power_activation,
                                   ursula_decentralized_test_config):

    mock_transacting_power_activation(account=staker.checksum_address, password=INSECURE_DEVELOPMENT_PASSWORD)

    staker.initialize_stake(amount=NU(token_economics.minimum_allowed_locked, 'NuNit'),
                            lock_periods=int(token_economics.minimum_locked_periods))

    # Get an unused address and create a new worker
    worker_address = testerchain.unassigned_accounts[-1]

    # Control time
    clock = Clock()
    WorkTracker.CLOCK = clock

    # Check that the worker is unbonded
    assert not Worker.worker_is_bonded(worker_address, test_registry)

    # Bond the Worker and Staker
    staker.set_worker(worker_address=worker_address)

    # Ensure the worker is now bonded
    assert Worker.worker_is_bonded(worker_address, test_registry)

    # Make the Worker
    ursula = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                        stakers_addresses=[staker.checksum_address],
                                        workers_addresses=[worker_address],
                                        confirm_activity=False,
                                        registry=test_registry).pop()

    def start():
        # Start running the worker
        start_pytest_ursula_services(ursula=ursula)
        ursula.work_tracker.start()

    def time_travel(_):
        testerchain.time_travel(periods=1)
        clock.advance(WorkTracker.REFRESH_RATE+1)

    def verify(_):
        # Verify that periods were confirmed on-chain automatically
        last_active_period = staker.staking_agent.get_last_active_period(staker_address=staker.checksum_address)
        current_period = staker.staking_agent.get_current_period()
        assert (last_active_period - current_period) == 1

    # Run the callbacks
    d = threads.deferToThread(start)
    for i in range(5):
        d.addCallback(time_travel)
        d.addCallback(verify)
    yield d
