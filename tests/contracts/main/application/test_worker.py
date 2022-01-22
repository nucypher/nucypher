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

from eth_tester.exceptions import TransactionFailed

from nucypher.blockchain.eth.constants import NULL_ADDRESS
from eth_utils import to_checksum_address
from constant_sorrow.constants import MOCK_DB
from tests.utils.ursula import start_pytest_ursula_services

CONFIRMATION_SLOT = 1


def test_bond_worker(testerchain, threshold_staking, pre_application, token_economics):
    creator, operator1, operator2, operator3, operator4, worker1, worker2, worker3, owner3, *everyone_else = \
        testerchain.client.accounts
    min_authorization = token_economics.minimum_allowed_locked
    min_worker_seconds = 24 * 60 * 60

    worker_log = pre_application.events.WorkerBonded.createFilter(fromBlock='latest')

    # Prepare operators: two with intermediary contract and two just an operator
    tx = threshold_staking.functions.setRoles(operator1).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(operator1, min_authorization, 0, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setRoles(operator2).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(
        operator2, min_authorization // 3, min_authorization // 3, min_authorization // 3 - 1).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setRoles(operator3, owner3, everyone_else[0], everyone_else[1]).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(operator3, 0, min_authorization, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setRoles(operator4).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(operator4, 0, 0, min_authorization).transact()
    testerchain.wait_for_receipt(tx)

    assert pre_application.functions.getWorkerFromOperator(operator1).call() == NULL_ADDRESS
    assert pre_application.functions.operatorFromWorker(operator1).call() == NULL_ADDRESS
    assert pre_application.functions.getWorkerFromOperator(operator2).call() == NULL_ADDRESS
    assert pre_application.functions.operatorFromWorker(operator2).call() == NULL_ADDRESS
    assert pre_application.functions.getWorkerFromOperator(operator3).call() == NULL_ADDRESS
    assert pre_application.functions.operatorFromWorker(operator3).call() == NULL_ADDRESS
    assert pre_application.functions.getWorkerFromOperator(operator4).call() == NULL_ADDRESS
    assert pre_application.functions.operatorFromWorker(operator4).call() == NULL_ADDRESS

    # Operator can't confirm worker address because there is no worker by default
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmWorkerAddress().transact({'from': operator1})
        testerchain.wait_for_receipt(tx)

    # Operator can't bond another operator as worker
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(operator1, operator2).transact({'from': operator1})
        testerchain.wait_for_receipt(tx)

    # Operator can't bond worker if stake is less than minimum
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(operator2, worker1).transact({'from': operator2})
        testerchain.wait_for_receipt(tx)

    # Only operator or stake owner can bond worker
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(operator3, worker1).transact({'from': everyone_else[0]})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(operator3, worker1).transact({'from': everyone_else[1]})
        testerchain.wait_for_receipt(tx)

    # Operator bonds worker and now worker can make a confirmation
    tx = pre_application.functions.bondWorker(operator3, worker1).transact({'from': owner3})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromOperator(operator3).call() == worker1
    assert pre_application.functions.operatorFromWorker(worker1).call() == operator3
    assert not pre_application.functions.operatorInfo(operator3).call()[CONFIRMATION_SLOT]
    assert not pre_application.functions.isWorkerConfirmed(worker1).call()
    assert pre_application.functions.getOperatorsLength().call() == 1
    assert pre_application.functions.operators(0).call() == operator3

    # No active operators before confirmation
    all_locked, operators = pre_application.functions.getActiveOperators(0, 0).call()
    assert all_locked == 0
    assert len(operators) == 0

    tx = pre_application.functions.confirmWorkerAddress().transact({'from': worker1})
    testerchain.wait_for_receipt(tx)
    assert pre_application.functions.operatorInfo(operator3).call()[CONFIRMATION_SLOT]
    assert pre_application.functions.isWorkerConfirmed(worker1).call()

    number_of_events = 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['operator'] == operator3
    assert event_args['worker'] == worker1
    assert event_args['startTimestamp'] == timestamp

    # After confirmation worker is becoming active
    all_locked, operators = pre_application.functions.getActiveOperators(0, 0).call()
    assert all_locked == min_authorization
    assert len(operators) == 1
    assert to_checksum_address(operators[0][0]) == operator3
    assert operators[0][1] == min_authorization

    # Worker is in use so other operators can't bond him
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(operator4, worker1).transact({'from': operator4})
        testerchain.wait_for_receipt(tx)

    # # Worker can't be an operator
    # tx = threshold_staking.functions.setRoles(worker1).transact()
    # testerchain.wait_for_receipt(tx)
    # tx = threshold_staking.functions.setStakes(worker1, min_authorization, 0, 0).transact()
    # testerchain.wait_for_receipt(tx)
    # with pytest.raises((TransactionFailed, ValueError)):
    #     tx = threshold_staking.functions.increaseAuthorization(
    #         worker1, min_authorization, pre_application.address).transact({'from': worker1})
    #     testerchain.wait_for_receipt(tx)

    # Can't bond worker twice too soon
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(operator3, worker2).transact({'from': operator3})
        testerchain.wait_for_receipt(tx)

    # She can't unbond her worker too, until enough time has passed
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(operator3, NULL_ADDRESS).transact({'from': operator3})
        testerchain.wait_for_receipt(tx)

    # Let's advance some time and unbond the worker
    testerchain.time_travel(seconds=min_worker_seconds)
    tx = pre_application.functions.bondWorker(operator3, NULL_ADDRESS).transact({'from': operator3})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromOperator(operator3).call() == NULL_ADDRESS
    assert pre_application.functions.operatorFromWorker(operator3).call() == NULL_ADDRESS
    assert pre_application.functions.operatorFromWorker(worker1).call() == NULL_ADDRESS
    assert not pre_application.functions.operatorInfo(operator3).call()[CONFIRMATION_SLOT]
    assert not pre_application.functions.isWorkerConfirmed(worker1).call()
    assert pre_application.functions.getOperatorsLength().call() == 1
    assert pre_application.functions.operators(0).call() == operator3

    # Resetting worker removes from active list before next confirmation
    all_locked, operators = pre_application.functions.getActiveOperators(0, 0).call()
    assert all_locked == 0
    assert len(operators) == 0

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['operator'] == operator3
    # Now the worker has been unbonded ...
    assert event_args['worker'] == NULL_ADDRESS
    # ... with a new starting period.
    assert event_args['startTimestamp'] == timestamp

    # The operator can bond now a new worker, without waiting additional time.
    tx = pre_application.functions.bondWorker(operator3, worker2).transact({'from': operator3})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromOperator(operator3).call() == worker2
    assert pre_application.functions.operatorFromWorker(worker2).call() == operator3
    assert not pre_application.functions.operatorInfo(operator3).call()[CONFIRMATION_SLOT]
    assert not pre_application.functions.isWorkerConfirmed(worker2).call()
    assert pre_application.functions.getOperatorsLength().call() == 1
    assert pre_application.functions.operators(0).call() == operator3

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['operator'] == operator3
    assert event_args['worker'] == worker2
    assert event_args['startTimestamp'] == timestamp

    # Now the previous worker can no longer make a confirmation
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmWorkerAddress().transact({'from': worker1})
        testerchain.wait_for_receipt(tx)
    # Only new worker can
    tx = pre_application.functions.confirmWorkerAddress().transact({'from': worker2})
    testerchain.wait_for_receipt(tx)
    assert not pre_application.functions.isWorkerConfirmed(worker1).call()
    assert pre_application.functions.isWorkerConfirmed(worker2).call()
    assert pre_application.functions.operatorInfo(operator3).call()[CONFIRMATION_SLOT]

    # Another staker can bond a free worker
    tx = pre_application.functions.bondWorker(operator4, worker1).transact({'from': operator4})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromOperator(operator4).call() == worker1
    assert pre_application.functions.operatorFromWorker(worker1).call() == operator4
    assert not pre_application.functions.isWorkerConfirmed(worker1).call()
    assert not pre_application.functions.operatorInfo(operator4).call()[CONFIRMATION_SLOT]
    assert pre_application.functions.getOperatorsLength().call() == 2
    assert pre_application.functions.operators(1).call() == operator4

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['operator'] == operator4
    assert event_args['worker'] == worker1
    assert event_args['startTimestamp'] == timestamp

    # # The first worker still can't be a staker
    # tx = threshold_staking.functions.setRoles(worker1).transact()
    # testerchain.wait_for_receipt(tx)
    # tx = threshold_staking.functions.setStakes(worker1, min_authorization, 0, 0).transact()
    # testerchain.wait_for_receipt(tx)
    # with pytest.raises((TransactionFailed, ValueError)):
    #     tx = threshold_staking.functions.increaseAuthorization(
    #         worker1, min_authorization, pre_application.address).transact({'from': worker1})
    #     testerchain.wait_for_receipt(tx)

    # Bond worker again
    tx = pre_application.functions.confirmWorkerAddress().transact({'from': worker1})
    testerchain.wait_for_receipt(tx)
    assert pre_application.functions.isWorkerConfirmed(worker1).call()
    assert pre_application.functions.operatorInfo(operator4).call()[CONFIRMATION_SLOT]
    testerchain.time_travel(seconds=min_worker_seconds)
    tx = pre_application.functions.bondWorker(operator4, worker3).transact({'from': operator4})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromOperator(operator4).call() == worker3
    assert pre_application.functions.operatorFromWorker(worker3).call() == operator4
    assert pre_application.functions.operatorFromWorker(worker1).call() == NULL_ADDRESS
    assert not pre_application.functions.isWorkerConfirmed(worker3).call()
    assert not pre_application.functions.isWorkerConfirmed(worker1).call()
    assert not pre_application.functions.operatorInfo(operator4).call()[CONFIRMATION_SLOT]
    assert pre_application.functions.getOperatorsLength().call() == 2
    assert pre_application.functions.operators(1).call() == operator4

    # Resetting worker removes from active list before next confirmation
    all_locked, operators = pre_application.functions.getActiveOperators(1, 0).call()
    assert all_locked == 0
    assert len(operators) == 0

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['operator'] == operator4
    assert event_args['worker'] == worker3
    assert event_args['startTimestamp'] == timestamp

    # The first worker is free and can deposit tokens and become a staker
    tx = threshold_staking.functions.setRoles(worker1).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(
        worker1, min_authorization // 3, min_authorization // 3, min_authorization // 3).transact()
    testerchain.wait_for_receipt(tx)
    # tx = threshold_staking.functions.increaseAuthorization(
    #     worker1, min_authorization, pre_application.address).transact({'from': worker1})
    # testerchain.wait_for_receipt(tx)
    assert pre_application.functions.getWorkerFromOperator(worker1).call() == NULL_ADDRESS
    assert pre_application.functions.operatorFromWorker(worker1).call() == NULL_ADDRESS

    # Operator can't bond the first worker again because worker is an operator now
    testerchain.time_travel(seconds=min_worker_seconds)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(operator4, worker1).transact({'from': operator4})
        testerchain.wait_for_receipt(tx)

    # Operator without intermediary contract can bond itself as worker
    # (Probably not best idea, but whatever)
    tx = pre_application.functions.bondWorker(operator1, operator1).transact({'from': operator1})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromOperator(operator1).call() == operator1
    assert pre_application.functions.operatorFromWorker(operator1).call() == operator1
    assert pre_application.functions.getOperatorsLength().call() == 3
    assert pre_application.functions.operators(2).call() == operator1

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['operator'] == operator1
    assert event_args['worker'] == operator1
    assert event_args['startTimestamp'] == timestamp

    # If stake will be less than minimum then confirmation is not possible
    tx = threshold_staking.functions.setStakes(operator1, 0, min_authorization - 1, 0).transact()
    testerchain.wait_for_receipt(tx)

    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmWorkerAddress().transact({'from': operator1})
        testerchain.wait_for_receipt(tx)

    # Now operator can make a confirmation
    tx = threshold_staking.functions.setStakes(operator1, 0, 0, min_authorization).transact()
    testerchain.wait_for_receipt(tx)
    tx = pre_application.functions.confirmWorkerAddress().transact({'from': operator1})
    testerchain.wait_for_receipt(tx)

    # If stake will be less than minimum then operator is not active
    all_locked, operators = pre_application.functions.getActiveOperators(0, 0).call()
    assert all_locked == 2 * min_authorization
    assert len(operators) == 2
    assert to_checksum_address(operators[0][0]) == operator3
    assert operators[0][1] == min_authorization
    assert to_checksum_address(operators[1][0]) == operator1
    assert operators[1][1] == min_authorization
    tx = threshold_staking.functions.setStakes(operator1, 0, min_authorization - 1, 0).transact()
    testerchain.wait_for_receipt(tx)
    all_locked, operators = pre_application.functions.getActiveOperators(1, 0).call()
    assert all_locked == 0
    assert len(operators) == 0


def test_confirm_address(testerchain, threshold_staking, pre_application, token_economics, deploy_contract):
    creator, operator, worker, *everyone_else = testerchain.client.accounts
    min_authorization = token_economics.minimum_allowed_locked
    min_worker_seconds = 24 * 60 * 60

    confirmations_log = pre_application.events.WorkerConfirmed.createFilter(fromBlock='latest')

    # Worker must be associated with operator that has minimum amount of tokens
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmWorkerAddress().transact({'from': operator})
        testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setRoles(operator).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(operator, min_authorization - 1, 0, 0).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmWorkerAddress().transact({'from': operator})
        testerchain.wait_for_receipt(tx)

    # Deploy intermediary contract
    intermediary, _ = deploy_contract('Intermediary', pre_application.address)

    # Bond contract as a worker
    tx = threshold_staking.functions.setStakes(operator, min_authorization, 0, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = pre_application.functions.bondWorker(operator, intermediary.address).transact({'from': operator})
    testerchain.wait_for_receipt(tx)

    # But can't make a confirmation using an intermediary contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary.functions.confirmWorkerAddress().transact({'from': operator})
        testerchain.wait_for_receipt(tx)

    # Bond worker again and make confirmation
    testerchain.time_travel(seconds=min_worker_seconds)
    tx = pre_application.functions.bondWorker(operator, worker).transact({'from': operator})
    testerchain.wait_for_receipt(tx)
    tx = pre_application.functions.confirmWorkerAddress().transact({'from': worker})
    testerchain.wait_for_receipt(tx)
    assert pre_application.functions.isWorkerConfirmed(worker).call()
    assert pre_application.functions.operatorInfo(operator).call()[CONFIRMATION_SLOT]

    events = confirmations_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['operator'] == operator
    assert event_args['worker'] == worker

    # Can't confirm twice
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmWorkerAddress().transact({'from': worker})
        testerchain.wait_for_receipt(tx)


def test_ursula_contract_interactions(ursula_decentralized_test_config, testerchain, threshold_staking, pre_application, token_economics, deploy_contract):
    creator, operator, worker_address, *everyone_else = testerchain.client.accounts
    min_authorization = token_economics.minimum_allowed_locked

    # make an operators and some stakes
    tx = threshold_staking.functions.setRoles(operator).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(operator, min_authorization, 0, 0).transact()
    testerchain.wait_for_receipt(tx)

    # make an ursula.
    blockchain_ursula = ursula_decentralized_test_config.produce(
        worker_address=worker_address,
        db_filepath=MOCK_DB,
        rest_port=9151)

    # it's not confirmed
    assert blockchain_ursula.is_confirmed is False

    # it has no operator
    assert blockchain_ursula.get_operator_address() == NULL_ADDRESS

    # now lets visit stake.nucypher.network and bond this worker
    tx = pre_application.functions.bondWorker(operator, worker_address).transact({'from': operator})
    testerchain.wait_for_receipt(tx)

    # now the worker has an operator
    assert blockchain_ursula.get_operator_address() == operator
    # but it still isn't confirmed
    assert blockchain_ursula.is_confirmed is False

    # lets confirm it.  It will probably do this automatically in real life...
    tx = blockchain_ursula.confirm_worker_address()
    testerchain.wait_for_receipt(tx.transactionHash)

    assert blockchain_ursula.is_confirmed is True


@pytest_twisted.inlineCallbacks
def test_worker_auto_confirm(mocker,
                                 testerchain,
                                 test_registry,
                                 staker,
                                 agency,
                                 token_economics,
                                 ursula_decentralized_test_config):

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
    replacement_spy = mocker.spy(WorkTracker, '_WorkTracker__fire_replacement_commitment')

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
        clock.advance(WorkTracker.INTERVAL_CEIL + 1)

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
        clock.advance(WorkTracker.INTERVAL_CEIL + 1)
        mocker.patch.object(WorkTracker, 'max_confirmation_time', return_value=1.0)
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
