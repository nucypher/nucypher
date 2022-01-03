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
from eth_tester.exceptions import TransactionFailed

from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.token import NU


CONFIRMATION_SLOT = 1


def test_bond_worker(testerchain, threshold_staking, pre_application, token_economics, deploy_contract):
    creator, operator1, operator2, operator3, worker1, worker2, worker3, *everyone_else = \
        testerchain.client.accounts
    min_authorization = token_economics.minimum_allowed_locked
    min_worker_seconds = 24 * 60 * 60

    worker_log = pre_application.events.WorkerBonded.createFilter(fromBlock='latest')

    # Deploy intermediary contracts
    intermediary1, _ = deploy_contract('Intermediary', pre_application.address)
    intermediary2, _ = deploy_contract('Intermediary', pre_application.address)
    intermediary3, _ = deploy_contract('Intermediary', pre_application.address)

    # Prepare operators: two with intermediary contract and two just an operator
    tx = threshold_staking.functions.setRoles(operator1, operator1, operator1, operator1).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(operator1, min_authorization, 0, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setRoles(operator2, operator2, operator2, operator2).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(
        operator2, min_authorization // 3, min_authorization // 3, min_authorization // 3 - 1).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setRoles(
        intermediary1.address, intermediary1.address, intermediary1.address, intermediary1.address).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(intermediary1.address, 0, min_authorization, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setRoles(
        intermediary2.address, intermediary2.address, intermediary2.address, intermediary2.address).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(intermediary2.address, 0, 0, min_authorization).transact()
    testerchain.wait_for_receipt(tx)

    assert pre_application.functions.getWorkerFromOperator(operator1).call() == NULL_ADDRESS
    assert pre_application.functions.operatorFromWorker(operator1).call() == NULL_ADDRESS
    assert pre_application.functions.getWorkerFromOperator(intermediary1.address).call() == NULL_ADDRESS
    assert pre_application.functions.operatorFromWorker(intermediary1.address).call() == NULL_ADDRESS
    assert pre_application.functions.getWorkerFromOperator(intermediary2.address).call() == NULL_ADDRESS
    assert pre_application.functions.operatorFromWorker(intermediary2.address).call() == NULL_ADDRESS

    # Operator can't confirm worker address because there is no worker by default
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary1.functions.confirmWorkerAddress().transact()
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmWorkerAddress().transact({'from': operator1})
        testerchain.wait_for_receipt(tx)

    # Operator can't bond another operator as worker
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary1.functions.bondWorker(operator2).transact()
        testerchain.wait_for_receipt(tx)

    # Operator can't bond worker if stake is less than minimum
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(worker1).transact({'from': operator2})
        testerchain.wait_for_receipt(tx)

    # Operator bonds worker and now worker can make a confirmation
    tx = intermediary1.functions.bondWorker(worker1).transact()
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromOperator(intermediary1.address).call() == worker1
    assert pre_application.functions.operatorFromWorker(worker1).call() == intermediary1.address
    assert not pre_application.functions.operatorInfo(intermediary1.address).call()[CONFIRMATION_SLOT]
    assert not pre_application.functions.isWorkerConfirmed(worker1).call()
    tx = pre_application.functions.confirmWorkerAddress().transact({'from': worker1})
    testerchain.wait_for_receipt(tx)
    assert pre_application.functions.operatorInfo(intermediary1.address).call()[CONFIRMATION_SLOT]
    assert pre_application.functions.isWorkerConfirmed(worker1).call()

    number_of_events = 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['operator'] == intermediary1.address
    assert event_args['worker'] == worker1
    assert event_args['startTimestamp'] == timestamp

    # Worker is in use so other operators can't bond him
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary2.functions.bondWorker(worker1).transact()
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
        tx = intermediary1.functions.bondWorker(worker2).transact()
        testerchain.wait_for_receipt(tx)

    # She can't unbond her worker too, until enough time has passed
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary1.functions.bondWorker(NULL_ADDRESS).transact()
        testerchain.wait_for_receipt(tx)

    # Let's advance some time and unbond the worker
    testerchain.time_travel(seconds=min_worker_seconds)
    tx = intermediary1.functions.bondWorker(NULL_ADDRESS).transact()
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromOperator(intermediary1.address).call() == NULL_ADDRESS
    assert pre_application.functions.operatorFromWorker(intermediary1.address).call() == NULL_ADDRESS
    assert pre_application.functions.operatorFromWorker(worker1).call() == NULL_ADDRESS
    assert not pre_application.functions.operatorInfo(intermediary1.address).call()[CONFIRMATION_SLOT]
    assert not pre_application.functions.isWorkerConfirmed(worker1).call()

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['operator'] == intermediary1.address
    # Now the worker has been unbonded ...
    assert event_args['worker'] == NULL_ADDRESS
    # ... with a new starting period.
    assert event_args['startTimestamp'] == timestamp

    # The operator can bond now a new worker, without waiting additional time.
    tx = intermediary1.functions.bondWorker(worker2).transact()
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromOperator(intermediary1.address).call() == worker2
    assert pre_application.functions.operatorFromWorker(worker2).call() == intermediary1.address
    assert not pre_application.functions.operatorInfo(intermediary1.address).call()[CONFIRMATION_SLOT]
    assert not pre_application.functions.isWorkerConfirmed(worker2).call()

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['operator'] == intermediary1.address
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
    assert pre_application.functions.operatorInfo(intermediary1.address).call()[CONFIRMATION_SLOT]

    # Another staker can bond a free worker
    tx = intermediary2.functions.bondWorker(worker1).transact()
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromOperator(intermediary2.address).call() == worker1
    assert pre_application.functions.operatorFromWorker(worker1).call() == intermediary2.address
    assert not pre_application.functions.isWorkerConfirmed(worker1).call()
    assert not pre_application.functions.operatorInfo(intermediary2.address).call()[CONFIRMATION_SLOT]

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['operator'] == intermediary2.address
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
    assert pre_application.functions.operatorInfo(intermediary2.address).call()[CONFIRMATION_SLOT]
    testerchain.time_travel(seconds=min_worker_seconds)
    tx = intermediary2.functions.bondWorker(operator3).transact()
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromOperator(intermediary2.address).call() == operator3
    assert pre_application.functions.operatorFromWorker(operator3).call() == intermediary2.address
    assert pre_application.functions.operatorFromWorker(worker1).call() == NULL_ADDRESS
    assert not pre_application.functions.isWorkerConfirmed(operator3).call()
    assert not pre_application.functions.isWorkerConfirmed(worker1).call()
    assert not pre_application.functions.operatorInfo(intermediary2.address).call()[CONFIRMATION_SLOT]

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['operator'] == intermediary2.address
    assert event_args['worker'] == operator3
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
        tx = intermediary1.functions.bondWorker(worker1).transact()
        testerchain.wait_for_receipt(tx)

    # Operator without intermediary contract can bond itself as worker
    # (Probably not best idea, but whatever)
    tx = pre_application.functions.bondWorker(operator1).transact({'from': operator1})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromOperator(operator1).call() == operator1
    assert pre_application.functions.operatorFromWorker(operator1).call() == operator1

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['operator'] == operator1
    assert event_args['worker'] == operator1
    assert event_args['startTimestamp'] == timestamp

    # Now operator can make a confirmation
    tx = pre_application.functions.confirmWorkerAddress().transact({'from': operator1})
    testerchain.wait_for_receipt(tx)

    # Operator try to bond contract as worker
    testerchain.time_travel(seconds=min_worker_seconds)
    tx = pre_application.functions.bondWorker(intermediary3.address).transact({'from': operator1})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['operator'] == operator1
    assert event_args['worker'] == intermediary3.address
    assert event_args['startTimestamp'] == timestamp

    # But can't make a confirmation using an intermediary contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary3.functions.confirmWorkerAddress().transact({'from': operator1})
        testerchain.wait_for_receipt(tx)
