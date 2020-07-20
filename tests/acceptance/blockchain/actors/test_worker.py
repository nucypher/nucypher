"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import pytest
import pytest_twisted
from twisted.internet import threads
from twisted.internet.task import Clock

from nucypher.blockchain.eth.actors import Worker
from nucypher.blockchain.eth.token import NU, WorkTracker
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD
from tests.utils.ursula import make_decentralized_ursulas, start_pytest_ursula_services


@pytest.mark.slow()
@pytest_twisted.inlineCallbacks
def test_worker_auto_commitments(mocker,
                                 testerchain,
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

    # Bond the Worker and Staker
    staker.bond_worker(worker_address=worker_address)

    commit_spy = mocker.spy(Worker, 'commit_to_next_period')

    # Make the Worker
    ursula = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                        stakers_addresses=[staker.checksum_address],
                                        workers_addresses=[worker_address],
                                        commit_to_next_period=False,
                                        registry=test_registry).pop()

    initial_period = staker.staking_agent.get_current_period()

    def start():
        # Start running the worker
        start_pytest_ursula_services(ursula=ursula)

    def time_travel(_):
        testerchain.time_travel(periods=1)
        clock.advance(WorkTracker.REFRESH_RATE+1)
        return clock

    def verify(clock):
        # Verify that periods were committed on-chain automatically
        last_committed_period = staker.staking_agent.get_last_committed_period(staker_address=staker.checksum_address)
        current_period = staker.staking_agent.get_current_period()
        assert (last_committed_period - current_period) == 1
        assert commit_spy.call_count == current_period - initial_period + 1

    # Run the callbacks
    d = threads.deferToThread(start)
    d.addCallback(verify)
    for i in range(5):
        d.addCallback(time_travel)
        d.addCallback(verify)
    yield d
