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
from web3.middleware.simulate_unmined_transaction import unmined_receipt_simulator_middleware

from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.agents import ContractAgency, PREApplicationAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.blockchain.eth.token import NU, WorkTracker
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.logging import Logger
from tests.utils.ursula import make_decentralized_ursulas, start_pytest_ursula_services
from constant_sorrow.constants import MOCK_DB

logger = Logger("test-operator")


def log(message):
    logger.debug(message)
    print(message)


@pytest.mark.skip()
@pytest_twisted.inlineCallbacks
def test_worker_auto_commitments(mocker,
                                 testerchain,
                                 test_registry,
                                 staker,
                                 agency,
                                 application_economics,
                                 ursula_decentralized_test_config):

    staker.initialize_stake(amount=NU(application_economics.min_authorization, 'NuNit'),
                            lock_periods=int(application_economics.min_operator_seconds))

    # Get an unused address and create a new worker
    worker_address = testerchain.unassigned_accounts[-1]

    # Control time
    clock = Clock()
    ClassicPREWorkTracker.CLOCK = clock

    # Bond the Worker and Staker
    staker.bond_worker(worker_address=worker_address)

    commit_spy = mocker.spy(Worker, 'commit_to_next_period')
    replacement_spy = mocker.spy(ClassicPREWorkTracker, '_ClassicPREWorkTracker__fire_replacement_commitment')

    # Make the Worker
    ursula = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                        stakers_addresses=[staker.checksum_address],
                                        workers_addresses=[worker_address],
                                        registry=test_registry).pop()

    ursula.run(preflight=False,
               discovery=False,
               start_reactor=False,
               worker=True,
               eager=True,
               block_until_ready=False)  # "start" services

    initial_period = staker.staking_agent.get_current_period()

    def start():
        log("Starting Worker for auto-commitment simulation")
        start_pytest_ursula_services(ursula=ursula)

    def advance_one_period(_):
        log('Advancing one period')
        testerchain.time_travel(periods=1)
        clock.advance(ClassicPREWorkTracker.INTERVAL_CEIL + 1)

    def check_pending_commitments(number_of_commitments):
        def _check_pending_commitments(_):
            log(f'Checking we have {number_of_commitments} pending commitments')
            assert number_of_commitments == len(ursula.work_tracker.pending)
        return _check_pending_commitments

    def pending_commitments(_):
        log('Starting unmined transaction simulation')
        testerchain.client.add_middleware(unmined_receipt_simulator_middleware)

    def advance_one_cycle(_):
        log('Advancing one tracking iteration')
        clock.advance(ursula.work_tracker._tracking_task.interval + 1)

    def advance_until_replacement_indicated(_):
        last_committed_period = staker.staking_agent.get_last_committed_period(staker_address=staker.checksum_address)
        log("Advancing until replacement is indicated")
        testerchain.time_travel(periods=1)
        clock.advance(ClassicPREWorkTracker.INTERVAL_CEIL + 1)
        mocker.patch.object(ClassicPREWorkTracker, 'max_confirmation_time', return_value=1.0)
        mock_last_committed_period = mocker.PropertyMock(return_value=last_committed_period)
        mocker.patch.object(Worker, 'last_committed_period', new_callable=mock_last_committed_period)
        clock.advance(ursula.work_tracker.max_confirmation_time() + 1)

    def verify_unmined_commitment(_):
        log('Verifying worker has unmined commitment transaction')

        # FIXME: The test doesn't model accurately an unmined TX, but an unconfirmed receipt,
        # so the tracker does not have pending TXs. If we want to model pending TXs we need to actually
        # prevent them from being mined.
        #
        # assert len(ursula.work_tracker.pending) == 1
        current_period = staker.staking_agent.get_current_period()
        assert commit_spy.call_count == current_period - initial_period + 1

    def verify_replacement_commitment(_):
        log('Verifying worker has replaced commitment transaction')
        assert replacement_spy.call_count > 0

    def verify_confirmed(_):
        # Verify that periods were committed on-chain automatically
        last_committed_period = staker.staking_agent.get_last_committed_period(staker_address=staker.checksum_address)
        current_period = staker.staking_agent.get_current_period()

        expected_commitments = current_period - initial_period + 1
        log(f'Verifying worker made {expected_commitments} commitments so far')
        assert (last_committed_period - current_period) == 1
        assert commit_spy.call_count == expected_commitments
        assert replacement_spy.call_count == 0

    # Behavioural Test, like a screenplay made of legos

    # Ursula commits on startup
    d = threads.deferToThread(start)
    d.addCallback(verify_confirmed)
    d.addCallback(advance_one_period)

    d.addCallback(check_pending_commitments(1))
    d.addCallback(advance_one_cycle)
    d.addCallback(check_pending_commitments(0))

    # Ursula commits for 3 periods with no problem
    for i in range(3):
        d.addCallback(advance_one_period)
        d.addCallback(verify_confirmed)
        d.addCallback(check_pending_commitments(1))

    # Introduce unmined transactions
    d.addCallback(advance_one_period)
    d.addCallback(pending_commitments)

    # Ursula's commitment transaction gets stuck
    for i in range(4):
        d.addCallback(advance_one_cycle)
        d.addCallback(verify_unmined_commitment)

    # Ursula recovers from this situation
    d.addCallback(advance_one_cycle)
    d.addCallback(verify_confirmed)
    d.addCallback(advance_one_cycle)
    d.addCallback(check_pending_commitments(0))

    # but it happens again, resulting in a replacement transaction
    d.addCallback(advance_until_replacement_indicated)
    d.addCallback(advance_one_cycle)
    d.addCallback(check_pending_commitments(1))
    d.addCallback(advance_one_cycle)
    d.addCallback(verify_replacement_commitment)

    yield d


def test_ursula_contract_interaction_methods(ursula_decentralized_test_config,
                                             testerchain,
                                             threshold_staking,
                                             agency,
                                             application_economics,
                                             test_registry):
    application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    creator, staking_provider, operator_address, *everyone_else = testerchain.client.accounts
    min_authorization = application_economics.min_authorization

    # make an staking_providers and some stakes
    tx = threshold_staking.functions.setRoles(staking_provider).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(staking_provider, min_authorization, 0, 0).transact()
    testerchain.wait_for_receipt(tx)

    # make an ursula.
    blockchain_ursula = ursula_decentralized_test_config.produce(
        operator_address=operator_address,
        db_filepath=MOCK_DB,
        rest_port=9151)

    # it's not confirmed
    assert blockchain_ursula.is_confirmed is False

    # it has no staking provider
    assert blockchain_ursula.get_staking_provider_address() == NULL_ADDRESS

    # now lets visit stake.nucypher.network and bond this operator
    tpower = TransactingPower(account=staking_provider, signer=Web3Signer(testerchain.client))
    application_agent.bond_operator(provider=staking_provider,
                                    operator=operator_address,
                                    transacting_power=tpower)

    # now the worker has a staking provider
    assert blockchain_ursula.get_staking_provider_address() == staking_provider
    # but it still isn't confirmed
    assert blockchain_ursula.is_confirmed is False

    # lets confirm it.  It will probably do this automatically in real life...
    tx = blockchain_ursula.confirm_operator_address()
    testerchain.wait_for_receipt(tx)

    assert blockchain_ursula.is_confirmed is True


@pytest_twisted.inlineCallbacks
def test_integration_of_ursula_contract_interaction(mocker,
                                                    ursula_decentralized_test_config,
                                                    testerchain,
                                                    threshold_staking,
                                                    agency,
                                                    application_economics,
                                                    test_registry):
    application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    creator, staking_provider, operator, staking_provider2, operator2, *everyone_else = testerchain.client.accounts
    min_authorization = application_economics.min_authorization

    commit_spy = mocker.spy(Operator, 'confirm_operator_address')
    # replacement_spy = mocker.spy(WorkTracker, '_WorkTracker__fire_replacement_commitment')

    # make an staking_providers and some stakes
    tx = threshold_staking.functions.setRoles(staking_provider2).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(staking_provider2, min_authorization, 0, 0).transact()
    testerchain.wait_for_receipt(tx)

    # now lets bond this worker
    tpower = TransactingPower(account=staking_provider2, signer=Web3Signer(testerchain.client))
    application_agent.bond_operator(provider=staking_provider2,
                                    operator=operator2,
                                    transacting_power=tpower)

    # Make the Operator
    ursula = ursula_decentralized_test_config.produce(
        operator_address=operator2,
        db_filepath=MOCK_DB,
        rest_port=9151)

    ursula.run(preflight=False,
               discovery=False,
               start_reactor=False,
               worker=True,
               eager=True,
               block_until_ready=True)  # "start" services

    def start():
        log("Starting Operator for auto confirm address simulation")
        start_pytest_ursula_services(ursula=ursula)

    def verify_confirmed(_):
        # Verify that periods were committed on-chain automatically
        expected_commitments = 1
        log(f'Verifying worker made {expected_commitments} commitments so far')
        assert commit_spy.call_count == expected_commitments
        # assert replacement_spy.call_count == 0

        assert application_agent.is_operator_confirmed(operator2)

    # Behavioural Test, like a screenplay made of legos

    # Ursula confirms on startup
    d = threads.deferToThread(start)
    d.addCallback(verify_confirmed)

    yield d
