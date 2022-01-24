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
from eth_utils import to_checksum_address

CONFIRMATION_SLOT = 1


def test_bond_worker(testerchain, threshold_staking, pre_application, token_economics):
    creator, staking_provider_1, staking_provider_2, staking_provider_3, staking_provider_4, \
    worker1, worker2, worker3, owner3, beneficiary, authorizer, *everyone_else = \
        testerchain.client.accounts
    min_authorization = token_economics.minimum_allowed_locked
    min_worker_seconds = 24 * 60 * 60

    worker_log = pre_application.events.WorkerBonded.createFilter(fromBlock='latest')

    # Prepare staking providers: two with intermediary contract and two just a staking provider
    tx = threshold_staking.functions.setRoles(staking_provider_1).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(staking_provider_1, min_authorization, 0, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setRoles(staking_provider_2).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(
        staking_provider_2, min_authorization // 3, min_authorization // 3, min_authorization // 3 - 1).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setRoles(staking_provider_3, owner3, beneficiary, authorizer).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(staking_provider_3, 0, min_authorization, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setRoles(staking_provider_4).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(staking_provider_4, 0, 0, min_authorization).transact()
    testerchain.wait_for_receipt(tx)

    assert pre_application.functions.getWorkerFromStakingProvider(staking_provider_1).call() == NULL_ADDRESS
    assert pre_application.functions.stakingProviderFromWorker(staking_provider_1).call() == NULL_ADDRESS
    assert pre_application.functions.getWorkerFromStakingProvider(staking_provider_2).call() == NULL_ADDRESS
    assert pre_application.functions.stakingProviderFromWorker(staking_provider_2).call() == NULL_ADDRESS
    assert pre_application.functions.getWorkerFromStakingProvider(staking_provider_3).call() == NULL_ADDRESS
    assert pre_application.functions.stakingProviderFromWorker(staking_provider_3).call() == NULL_ADDRESS
    assert pre_application.functions.getWorkerFromStakingProvider(staking_provider_4).call() == NULL_ADDRESS
    assert pre_application.functions.stakingProviderFromWorker(staking_provider_4).call() == NULL_ADDRESS

    # Staking provider can't confirm worker address because there is no worker by default
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmWorkerAddress().transact({'from': staking_provider_1})
        testerchain.wait_for_receipt(tx)

    # Staking provider can't bond another staking provider as worker
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(staking_provider_1, staking_provider_2).transact({'from': staking_provider_1})
        testerchain.wait_for_receipt(tx)

    # Staking provider can't bond worker if stake is less than minimum
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(staking_provider_2, worker1).transact({'from': staking_provider_2})
        testerchain.wait_for_receipt(tx)

    # Only staking provider or stake owner can bond worker
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(staking_provider_3, worker1).transact({'from': beneficiary})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(staking_provider_3, worker1).transact({'from': authorizer})
        testerchain.wait_for_receipt(tx)

    # Staking provider bonds worker and now worker can make a confirmation
    tx = pre_application.functions.bondWorker(staking_provider_3, worker1).transact({'from': owner3})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromStakingProvider(staking_provider_3).call() == worker1
    assert pre_application.functions.stakingProviderFromWorker(worker1).call() == staking_provider_3
    assert not pre_application.functions.stakingProviderInfo(staking_provider_3).call()[CONFIRMATION_SLOT]
    assert not pre_application.functions.isWorkerConfirmed(worker1).call()
    assert pre_application.functions.getStakingProvidersLength().call() == 1
    assert pre_application.functions.stakingProviders(0).call() == staking_provider_3

    # No active stakingProviders before confirmation
    all_locked, staking_providers = pre_application.functions.getActiveStakingProviders(0, 0).call()
    assert all_locked == 0
    assert len(staking_providers) == 0

    tx = pre_application.functions.confirmWorkerAddress().transact({'from': worker1})
    testerchain.wait_for_receipt(tx)
    assert pre_application.functions.stakingProviderInfo(staking_provider_3).call()[CONFIRMATION_SLOT]
    assert pre_application.functions.isWorkerConfirmed(worker1).call()

    number_of_events = 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['stakingProvider'] == staking_provider_3
    assert event_args['worker'] == worker1
    assert event_args['startTimestamp'] == timestamp

    # After confirmation worker is becoming active
    all_locked, staking_providers = pre_application.functions.getActiveStakingProviders(0, 0).call()
    assert all_locked == min_authorization
    assert len(staking_providers) == 1
    assert to_checksum_address(staking_providers[0][0]) == staking_provider_3
    assert staking_providers[0][1] == min_authorization

    # Worker is in use so other stakingProviders can't bond him
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(staking_provider_4, worker1).transact({'from': staking_provider_4})
        testerchain.wait_for_receipt(tx)

    # # Worker can't be a staking provider
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
        tx = pre_application.functions.bondWorker(staking_provider_3, worker2).transact({'from': staking_provider_3})
        testerchain.wait_for_receipt(tx)

    # She can't unbond her worker too, until enough time has passed
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(staking_provider_3, NULL_ADDRESS).transact({'from': staking_provider_3})
        testerchain.wait_for_receipt(tx)

    # Let's advance some time and unbond the worker
    testerchain.time_travel(seconds=min_worker_seconds)
    tx = pre_application.functions.bondWorker(staking_provider_3, NULL_ADDRESS).transact({'from': staking_provider_3})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromStakingProvider(staking_provider_3).call() == NULL_ADDRESS
    assert pre_application.functions.stakingProviderFromWorker(staking_provider_3).call() == NULL_ADDRESS
    assert pre_application.functions.stakingProviderFromWorker(worker1).call() == NULL_ADDRESS
    assert not pre_application.functions.stakingProviderInfo(staking_provider_3).call()[CONFIRMATION_SLOT]
    assert not pre_application.functions.isWorkerConfirmed(worker1).call()
    assert pre_application.functions.getStakingProvidersLength().call() == 1
    assert pre_application.functions.stakingProviders(0).call() == staking_provider_3

    # Resetting worker removes from active list before next confirmation
    all_locked, staking_providers = pre_application.functions.getActiveStakingProviders(0, 0).call()
    assert all_locked == 0
    assert len(staking_providers) == 0

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['stakingProvider'] == staking_provider_3
    # Now the worker has been unbonded ...
    assert event_args['worker'] == NULL_ADDRESS
    # ... with a new starting period.
    assert event_args['startTimestamp'] == timestamp

    # The staking provider can bond now a new worker, without waiting additional time.
    tx = pre_application.functions.bondWorker(staking_provider_3, worker2).transact({'from': staking_provider_3})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromStakingProvider(staking_provider_3).call() == worker2
    assert pre_application.functions.stakingProviderFromWorker(worker2).call() == staking_provider_3
    assert not pre_application.functions.stakingProviderInfo(staking_provider_3).call()[CONFIRMATION_SLOT]
    assert not pre_application.functions.isWorkerConfirmed(worker2).call()
    assert pre_application.functions.getStakingProvidersLength().call() == 1
    assert pre_application.functions.stakingProviders(0).call() == staking_provider_3

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['stakingProvider'] == staking_provider_3
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
    assert pre_application.functions.stakingProviderInfo(staking_provider_3).call()[CONFIRMATION_SLOT]

    # Another staker can bond a free worker
    tx = pre_application.functions.bondWorker(staking_provider_4, worker1).transact({'from': staking_provider_4})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromStakingProvider(staking_provider_4).call() == worker1
    assert pre_application.functions.stakingProviderFromWorker(worker1).call() == staking_provider_4
    assert not pre_application.functions.isWorkerConfirmed(worker1).call()
    assert not pre_application.functions.stakingProviderInfo(staking_provider_4).call()[CONFIRMATION_SLOT]
    assert pre_application.functions.getStakingProvidersLength().call() == 2
    assert pre_application.functions.stakingProviders(1).call() == staking_provider_4

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['stakingProvider'] == staking_provider_4
    assert event_args['worker'] == worker1
    assert event_args['startTimestamp'] == timestamp

    # # The first worker still can't be a staking provider
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
    assert pre_application.functions.stakingProviderInfo(staking_provider_4).call()[CONFIRMATION_SLOT]
    testerchain.time_travel(seconds=min_worker_seconds)
    tx = pre_application.functions.bondWorker(staking_provider_4, worker3).transact({'from': staking_provider_4})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromStakingProvider(staking_provider_4).call() == worker3
    assert pre_application.functions.stakingProviderFromWorker(worker3).call() == staking_provider_4
    assert pre_application.functions.stakingProviderFromWorker(worker1).call() == NULL_ADDRESS
    assert not pre_application.functions.isWorkerConfirmed(worker3).call()
    assert not pre_application.functions.isWorkerConfirmed(worker1).call()
    assert not pre_application.functions.stakingProviderInfo(staking_provider_4).call()[CONFIRMATION_SLOT]
    assert pre_application.functions.getStakingProvidersLength().call() == 2
    assert pre_application.functions.stakingProviders(1).call() == staking_provider_4

    # Resetting worker removes from active list before next confirmation
    all_locked, staking_providers = pre_application.functions.getActiveStakingProviders(1, 0).call()
    assert all_locked == 0
    assert len(staking_providers) == 0

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['stakingProvider'] == staking_provider_4
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
    assert pre_application.functions.getWorkerFromStakingProvider(worker1).call() == NULL_ADDRESS
    assert pre_application.functions.stakingProviderFromWorker(worker1).call() == NULL_ADDRESS

    testerchain.time_travel(seconds=min_worker_seconds)

    # Staking provider can't bond the first worker again because worker is a provider now
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondWorker(staking_provider_4, worker1).transact({'from': staking_provider_4})
        testerchain.wait_for_receipt(tx)

    # Provider without intermediary contract can bond itself as worker
    # (Probably not best idea, but whatever)
    tx = pre_application.functions.bondWorker(
        staking_provider_1, staking_provider_1).transact({'from': staking_provider_1})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getWorkerFromStakingProvider(staking_provider_1).call() == staking_provider_1
    assert pre_application.functions.stakingProviderFromWorker(staking_provider_1).call() == staking_provider_1
    assert pre_application.functions.getStakingProvidersLength().call() == 3
    assert pre_application.functions.stakingProviders(2).call() == staking_provider_1

    number_of_events += 1
    events = worker_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['stakingProvider'] == staking_provider_1
    assert event_args['worker'] == staking_provider_1
    assert event_args['startTimestamp'] == timestamp

    # If stake will be less than minimum then confirmation is not possible
    tx = threshold_staking.functions.setStakes(staking_provider_1, 0, min_authorization - 1, 0).transact()
    testerchain.wait_for_receipt(tx)

    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmWorkerAddress().transact({'from': staking_provider_1})
        testerchain.wait_for_receipt(tx)

    # Now provider can make a confirmation
    tx = threshold_staking.functions.setStakes(staking_provider_1, 0, 0, min_authorization).transact()
    testerchain.wait_for_receipt(tx)
    tx = pre_application.functions.confirmWorkerAddress().transact({'from': staking_provider_1})
    testerchain.wait_for_receipt(tx)

    # If stake will be less than minimum then provider is not active
    all_locked, staking_providers = pre_application.functions.getActiveStakingProviders(0, 0).call()
    assert all_locked == 2 * min_authorization
    assert len(staking_providers) == 2
    assert to_checksum_address(staking_providers[0][0]) == staking_provider_3
    assert staking_providers[0][1] == min_authorization
    assert to_checksum_address(staking_providers[1][0]) == staking_provider_1
    assert staking_providers[1][1] == min_authorization
    tx = threshold_staking.functions.setStakes(staking_provider_1, 0, min_authorization - 1, 0).transact()
    testerchain.wait_for_receipt(tx)
    all_locked, staking_providers = pre_application.functions.getActiveStakingProviders(1, 0).call()
    assert all_locked == 0
    assert len(staking_providers) == 0


def test_confirm_address(testerchain, threshold_staking, pre_application, token_economics, deploy_contract):
    creator, staking_provider, worker, *everyone_else = testerchain.client.accounts
    min_authorization = token_economics.minimum_allowed_locked
    min_worker_seconds = 24 * 60 * 60

    confirmations_log = pre_application.events.WorkerConfirmed.createFilter(fromBlock='latest')

    # Worker must be associated with provider that has minimum amount of tokens
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmWorkerAddress().transact({'from': staking_provider})
        testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setRoles(staking_provider).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(staking_provider, min_authorization - 1, 0, 0).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmWorkerAddress().transact({'from': staking_provider})
        testerchain.wait_for_receipt(tx)

    # Deploy intermediary contract
    intermediary, _ = deploy_contract('Intermediary', pre_application.address)

    # Bond contract as a worker
    tx = threshold_staking.functions.setStakes(staking_provider, min_authorization, 0, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = pre_application.functions.bondWorker(staking_provider, intermediary.address).transact({'from': staking_provider})
    testerchain.wait_for_receipt(tx)

    # But can't make a confirmation using an intermediary contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary.functions.confirmWorkerAddress().transact({'from': staking_provider})
        testerchain.wait_for_receipt(tx)

    # Bond worker again and make confirmation
    testerchain.time_travel(seconds=min_worker_seconds)
    tx = pre_application.functions.bondWorker(staking_provider, worker).transact({'from': staking_provider})
    testerchain.wait_for_receipt(tx)
    tx = pre_application.functions.confirmWorkerAddress().transact({'from': worker})
    testerchain.wait_for_receipt(tx)
    assert pre_application.functions.isWorkerConfirmed(worker).call()
    assert pre_application.functions.stakingProviderInfo(staking_provider).call()[CONFIRMATION_SLOT]

    events = confirmations_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['stakingProvider'] == staking_provider
    assert event_args['worker'] == worker

    # Can't confirm twice
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmWorkerAddress().transact({'from': worker})
        testerchain.wait_for_receipt(tx)
