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


def test_bond_operator(testerchain, threshold_staking, pre_application, application_economics):
    creator, staking_provider_1, staking_provider_2, staking_provider_3, staking_provider_4, \
    operator1, operator2, operator3, owner3, beneficiary, authorizer, *everyone_else = \
        testerchain.client.accounts
    min_authorization = application_economics.min_authorization
    min_operator_seconds = application_economics.min_operator_seconds

    operator_log = pre_application.events.OperatorBonded.createFilter(fromBlock='latest')

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

    assert pre_application.functions.getOperatorFromStakingProvider(staking_provider_1).call() == NULL_ADDRESS
    assert pre_application.functions.stakingProviderFromOperator(staking_provider_1).call() == NULL_ADDRESS
    assert pre_application.functions.getOperatorFromStakingProvider(staking_provider_2).call() == NULL_ADDRESS
    assert pre_application.functions.stakingProviderFromOperator(staking_provider_2).call() == NULL_ADDRESS
    assert pre_application.functions.getOperatorFromStakingProvider(staking_provider_3).call() == NULL_ADDRESS
    assert pre_application.functions.stakingProviderFromOperator(staking_provider_3).call() == NULL_ADDRESS
    assert pre_application.functions.getOperatorFromStakingProvider(staking_provider_4).call() == NULL_ADDRESS
    assert pre_application.functions.stakingProviderFromOperator(staking_provider_4).call() == NULL_ADDRESS

    # Staking provider can't confirm operator address because there is no operator by default
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmOperatorAddress().transact({'from': staking_provider_1})
        testerchain.wait_for_receipt(tx)

    # Staking provider can't bond another staking provider as operator
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondOperator(staking_provider_1, staking_provider_2)\
            .transact({'from': staking_provider_1})
        testerchain.wait_for_receipt(tx)

    # Staking provider can't bond operator if stake is less than minimum
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondOperator(staking_provider_2, operator1)\
            .transact({'from': staking_provider_2})
        testerchain.wait_for_receipt(tx)

    # Only staking provider or stake owner can bond operator
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondOperator(staking_provider_3, operator1).transact({'from': beneficiary})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondOperator(staking_provider_3, operator1).transact({'from': authorizer})
        testerchain.wait_for_receipt(tx)

    # Staking provider bonds operator and now operator can make a confirmation
    tx = pre_application.functions.bondOperator(staking_provider_3, operator1).transact({'from': owner3})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getOperatorFromStakingProvider(staking_provider_3).call() == operator1
    assert pre_application.functions.stakingProviderFromOperator(operator1).call() == staking_provider_3
    assert not pre_application.functions.stakingProviderInfo(staking_provider_3).call()[CONFIRMATION_SLOT]
    assert not pre_application.functions.isOperatorConfirmed(operator1).call()
    assert pre_application.functions.getStakingProvidersLength().call() == 1
    assert pre_application.functions.stakingProviders(0).call() == staking_provider_3

    # No active stakingProviders before confirmation
    all_locked, staking_providers = pre_application.functions.getActiveStakingProviders(0, 0).call()
    assert all_locked == 0
    assert len(staking_providers) == 0

    tx = pre_application.functions.confirmOperatorAddress().transact({'from': operator1})
    testerchain.wait_for_receipt(tx)
    assert pre_application.functions.stakingProviderInfo(staking_provider_3).call()[CONFIRMATION_SLOT]
    assert pre_application.functions.isOperatorConfirmed(operator1).call()

    number_of_events = 1
    events = operator_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['stakingProvider'] == staking_provider_3
    assert event_args['operator'] == operator1
    assert event_args['startTimestamp'] == timestamp

    # After confirmation operator is becoming active
    all_locked, staking_providers = pre_application.functions.getActiveStakingProviders(0, 0).call()
    assert all_locked == min_authorization
    assert len(staking_providers) == 1
    assert to_checksum_address(staking_providers[0][0]) == staking_provider_3
    assert staking_providers[0][1] == min_authorization

    # Operator is in use so other stakingProviders can't bond him
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondOperator(staking_provider_4, operator1).transact({'from': staking_provider_4})
        testerchain.wait_for_receipt(tx)

    # # Operator can't be a staking provider
    # tx = threshold_staking.functions.setRoles(operator1).transact()
    # testerchain.wait_for_receipt(tx)
    # tx = threshold_staking.functions.setStakes(operator1, min_authorization, 0, 0).transact()
    # testerchain.wait_for_receipt(tx)
    # with pytest.raises((TransactionFailed, ValueError)):
    #     tx = threshold_staking.functions.increaseAuthorization(
    #         operator1, min_authorization, pre_application.address).transact({'from': operator1})
    #     testerchain.wait_for_receipt(tx)

    # Can't bond operator twice too soon
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondOperator(staking_provider_3, operator2).transact({'from': staking_provider_3})
        testerchain.wait_for_receipt(tx)

    # She can't unbond her operator too, until enough time has passed
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondOperator(staking_provider_3, NULL_ADDRESS).transact({'from': staking_provider_3})
        testerchain.wait_for_receipt(tx)

    # Let's advance some time and unbond the operator
    testerchain.time_travel(seconds=min_operator_seconds)
    tx = pre_application.functions.bondOperator(staking_provider_3, NULL_ADDRESS).transact({'from': staking_provider_3})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getOperatorFromStakingProvider(staking_provider_3).call() == NULL_ADDRESS
    assert pre_application.functions.stakingProviderFromOperator(staking_provider_3).call() == NULL_ADDRESS
    assert pre_application.functions.stakingProviderFromOperator(operator1).call() == NULL_ADDRESS
    assert not pre_application.functions.stakingProviderInfo(staking_provider_3).call()[CONFIRMATION_SLOT]
    assert not pre_application.functions.isOperatorConfirmed(operator1).call()
    assert pre_application.functions.getStakingProvidersLength().call() == 1
    assert pre_application.functions.stakingProviders(0).call() == staking_provider_3

    # Resetting operator removes from active list before next confirmation
    all_locked, staking_providers = pre_application.functions.getActiveStakingProviders(0, 0).call()
    assert all_locked == 0
    assert len(staking_providers) == 0

    number_of_events += 1
    events = operator_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['stakingProvider'] == staking_provider_3
    # Now the operator has been unbonded ...
    assert event_args['operator'] == NULL_ADDRESS
    # ... with a new starting period.
    assert event_args['startTimestamp'] == timestamp

    # The staking provider can bond now a new operator, without waiting additional time.
    tx = pre_application.functions.bondOperator(staking_provider_3, operator2).transact({'from': staking_provider_3})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getOperatorFromStakingProvider(staking_provider_3).call() == operator2
    assert pre_application.functions.stakingProviderFromOperator(operator2).call() == staking_provider_3
    assert not pre_application.functions.stakingProviderInfo(staking_provider_3).call()[CONFIRMATION_SLOT]
    assert not pre_application.functions.isOperatorConfirmed(operator2).call()
    assert pre_application.functions.getStakingProvidersLength().call() == 1
    assert pre_application.functions.stakingProviders(0).call() == staking_provider_3

    number_of_events += 1
    events = operator_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['stakingProvider'] == staking_provider_3
    assert event_args['operator'] == operator2
    assert event_args['startTimestamp'] == timestamp

    # Now the previous operator can no longer make a confirmation
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmOperatorAddress().transact({'from': operator1})
        testerchain.wait_for_receipt(tx)
    # Only new operator can
    tx = pre_application.functions.confirmOperatorAddress().transact({'from': operator2})
    testerchain.wait_for_receipt(tx)
    assert not pre_application.functions.isOperatorConfirmed(operator1).call()
    assert pre_application.functions.isOperatorConfirmed(operator2).call()
    assert pre_application.functions.stakingProviderInfo(staking_provider_3).call()[CONFIRMATION_SLOT]

    # Another staker can bond a free operator
    tx = pre_application.functions.bondOperator(staking_provider_4, operator1).transact({'from': staking_provider_4})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getOperatorFromStakingProvider(staking_provider_4).call() == operator1
    assert pre_application.functions.stakingProviderFromOperator(operator1).call() == staking_provider_4
    assert not pre_application.functions.isOperatorConfirmed(operator1).call()
    assert not pre_application.functions.stakingProviderInfo(staking_provider_4).call()[CONFIRMATION_SLOT]
    assert pre_application.functions.getStakingProvidersLength().call() == 2
    assert pre_application.functions.stakingProviders(1).call() == staking_provider_4

    number_of_events += 1
    events = operator_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['stakingProvider'] == staking_provider_4
    assert event_args['operator'] == operator1
    assert event_args['startTimestamp'] == timestamp

    # # The first operator still can't be a staking provider
    # tx = threshold_staking.functions.setRoles(operator1).transact()
    # testerchain.wait_for_receipt(tx)
    # tx = threshold_staking.functions.setStakes(operator1, min_authorization, 0, 0).transact()
    # testerchain.wait_for_receipt(tx)
    # with pytest.raises((TransactionFailed, ValueError)):
    #     tx = threshold_staking.functions.increaseAuthorization(
    #         operator1, min_authorization, pre_application.address).transact({'from': operator1})
    #     testerchain.wait_for_receipt(tx)

    # Bond operator again
    tx = pre_application.functions.confirmOperatorAddress().transact({'from': operator1})
    testerchain.wait_for_receipt(tx)
    assert pre_application.functions.isOperatorConfirmed(operator1).call()
    assert pre_application.functions.stakingProviderInfo(staking_provider_4).call()[CONFIRMATION_SLOT]
    testerchain.time_travel(seconds=min_operator_seconds)
    tx = pre_application.functions.bondOperator(staking_provider_4, operator3).transact({'from': staking_provider_4})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getOperatorFromStakingProvider(staking_provider_4).call() == operator3
    assert pre_application.functions.stakingProviderFromOperator(operator3).call() == staking_provider_4
    assert pre_application.functions.stakingProviderFromOperator(operator1).call() == NULL_ADDRESS
    assert not pre_application.functions.isOperatorConfirmed(operator3).call()
    assert not pre_application.functions.isOperatorConfirmed(operator1).call()
    assert not pre_application.functions.stakingProviderInfo(staking_provider_4).call()[CONFIRMATION_SLOT]
    assert pre_application.functions.getStakingProvidersLength().call() == 2
    assert pre_application.functions.stakingProviders(1).call() == staking_provider_4

    # Resetting operator removes from active list before next confirmation
    all_locked, staking_providers = pre_application.functions.getActiveStakingProviders(1, 0).call()
    assert all_locked == 0
    assert len(staking_providers) == 0

    number_of_events += 1
    events = operator_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['stakingProvider'] == staking_provider_4
    assert event_args['operator'] == operator3
    assert event_args['startTimestamp'] == timestamp

    # The first operator is free and can deposit tokens and become a staker
    tx = threshold_staking.functions.setRoles(operator1).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(
        operator1, min_authorization // 3, min_authorization // 3, min_authorization // 3).transact()
    testerchain.wait_for_receipt(tx)
    # tx = threshold_staking.functions.increaseAuthorization(
    #     operator1, min_authorization, pre_application.address).transact({'from': operator1})
    # testerchain.wait_for_receipt(tx)
    assert pre_application.functions.getOperatorFromStakingProvider(operator1).call() == NULL_ADDRESS
    assert pre_application.functions.stakingProviderFromOperator(operator1).call() == NULL_ADDRESS

    testerchain.time_travel(seconds=min_operator_seconds)

    # Staking provider can't bond the first operator again because operator is a provider now
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.bondOperator(staking_provider_4, operator1).transact({'from': staking_provider_4})
        testerchain.wait_for_receipt(tx)

    # Provider without intermediary contract can bond itself as operator
    # (Probably not best idea, but whatever)
    tx = pre_application.functions.bondOperator(
        staking_provider_1, staking_provider_1).transact({'from': staking_provider_1})
    testerchain.wait_for_receipt(tx)
    timestamp = testerchain.w3.eth.getBlock('latest').timestamp
    assert pre_application.functions.getOperatorFromStakingProvider(staking_provider_1).call() == staking_provider_1
    assert pre_application.functions.stakingProviderFromOperator(staking_provider_1).call() == staking_provider_1
    assert pre_application.functions.getStakingProvidersLength().call() == 3
    assert pre_application.functions.stakingProviders(2).call() == staking_provider_1

    number_of_events += 1
    events = operator_log.get_all_entries()
    assert len(events) == number_of_events
    event_args = events[-1]['args']
    assert event_args['stakingProvider'] == staking_provider_1
    assert event_args['operator'] == staking_provider_1
    assert event_args['startTimestamp'] == timestamp

    # If stake will be less than minimum then confirmation is not possible
    tx = threshold_staking.functions.setStakes(staking_provider_1, 0, min_authorization - 1, 0).transact()
    testerchain.wait_for_receipt(tx)

    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmOperatorAddress().transact({'from': staking_provider_1})
        testerchain.wait_for_receipt(tx)

    # Now provider can make a confirmation
    tx = threshold_staking.functions.setStakes(staking_provider_1, 0, 0, min_authorization).transact()
    testerchain.wait_for_receipt(tx)
    tx = pre_application.functions.confirmOperatorAddress().transact({'from': staking_provider_1})
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


def test_confirm_address(testerchain, threshold_staking, pre_application, application_economics, deploy_contract):
    creator, staking_provider, operator, *everyone_else = testerchain.client.accounts
    min_authorization = application_economics.min_authorization
    min_operator_seconds = application_economics.min_operator_seconds

    confirmations_log = pre_application.events.OperatorConfirmed.createFilter(fromBlock='latest')

    # Operator must be associated with provider that has minimum amount of tokens
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmOperatorAddress().transact({'from': staking_provider})
        testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setRoles(staking_provider).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(staking_provider, min_authorization - 1, 0, 0).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmOperatorAddress().transact({'from': staking_provider})
        testerchain.wait_for_receipt(tx)

    # Deploy intermediary contract
    intermediary, _ = deploy_contract('Intermediary', pre_application.address)

    # Bond contract as an operator
    tx = threshold_staking.functions.setStakes(staking_provider, min_authorization, 0, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = pre_application.functions.bondOperator(staking_provider, intermediary.address).transact({'from': staking_provider})
    testerchain.wait_for_receipt(tx)

    # But can't make a confirmation using an intermediary contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = intermediary.functions.confirmOperatorAddress().transact({'from': staking_provider})
        testerchain.wait_for_receipt(tx)

    # Bond operator again and make confirmation
    testerchain.time_travel(seconds=min_operator_seconds)
    tx = pre_application.functions.bondOperator(staking_provider, operator).transact({'from': staking_provider})
    testerchain.wait_for_receipt(tx)
    tx = pre_application.functions.confirmOperatorAddress().transact({'from': operator})
    testerchain.wait_for_receipt(tx)
    assert pre_application.functions.isOperatorConfirmed(operator).call()
    assert pre_application.functions.stakingProviderInfo(staking_provider).call()[CONFIRMATION_SLOT]

    events = confirmations_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['stakingProvider'] == staking_provider
    assert event_args['operator'] == operator

    # Can't confirm twice
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pre_application.functions.confirmOperatorAddress().transact({'from': operator})
        testerchain.wait_for_receipt(tx)
