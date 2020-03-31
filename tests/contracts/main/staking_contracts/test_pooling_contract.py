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
from web3.contract import Contract

from nucypher.blockchain.eth.token import NU


BASE_OWNER_COEFFICIENT = int(NU.from_tokens(100_000))


@pytest.fixture()
def pooling_contract(testerchain, router, deploy_contract):
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]

    contract, _ = deploy_contract('PoolingStakingContract', router.address, BASE_OWNER_COEFFICIENT)

    # Transfer ownership
    tx = contract.functions.transferOwnership(owner).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    return contract


@pytest.fixture()
def pooling_contract_interface(testerchain, staking_interface, pooling_contract):
    return testerchain.client.get_contract(
        abi=staking_interface.abi,
        address=pooling_contract.address,
        ContractFactoryClass=Contract)


@pytest.mark.slow
def test_staking(testerchain, token_economics, token, escrow, pooling_contract, pooling_contract_interface):
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]
    delegators = testerchain.client.accounts[2:5]
    deposit_log = pooling_contract.events.TokensDeposited.createFilter(fromBlock='latest')
    withdraw_log = pooling_contract.events.TokensWithdrawn.createFilter(fromBlock='latest')

    assert pooling_contract.functions.baseCoefficient().call() == BASE_OWNER_COEFFICIENT
    assert pooling_contract.functions.withdrawnTokens().call() == 0
    assert pooling_contract.functions.delegators(owner).call() == [BASE_OWNER_COEFFICIENT, 0]
    assert token.functions.balanceOf(pooling_contract.address).call() == 0

    # Give some tokens to the owner
    tx = token.functions.transfer(owner, token_economics.minimum_allowed_locked).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert pooling_contract.functions.delegators(owner).call() == [BASE_OWNER_COEFFICIENT, 0]

    # Give some tokens to delegators
    for index, delegator in enumerate(delegators):
        tokens = token_economics.minimum_allowed_locked // (index + 1)
        tx = token.functions.transfer(delegator, tokens).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Delegators deposit tokens to the pooling contract
    base_coefficient = BASE_OWNER_COEFFICIENT
    tokens_supply = 0
    for index, delegator in enumerate(delegators):
        assert pooling_contract.functions.delegators(delegator).call() == [0, 0]
        tokens = token.functions.balanceOf(delegator).call() // 2
        tx = token.functions.approve(pooling_contract.address, tokens).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)
        tx = pooling_contract.functions.depositTokens(tokens).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)
        assert pooling_contract.functions.delegators(delegator).call() == [tokens, 0]
        base_coefficient += tokens
        tokens_supply += tokens
        assert pooling_contract.functions.baseCoefficient().call() == base_coefficient
        assert token.functions.balanceOf(pooling_contract.address).call() == tokens_supply

        events = deposit_log.get_all_entries()
        assert len(events) == index + 1
        event_args = events[-1]['args']
        assert event_args['sender'] == delegator
        assert event_args['value'] == tokens
        assert event_args['coefficient'] == tokens

    assert pooling_contract.functions.withdrawnTokens().call() == 0
    assert pooling_contract.functions.delegators(owner).call() == [BASE_OWNER_COEFFICIENT, 0]

    # Owner also deposits some tokens
    tokens = token.functions.balanceOf(owner).call()
    tx = token.functions.approve(pooling_contract.address, tokens).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    tx = pooling_contract.functions.depositTokens(tokens).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert pooling_contract.functions.delegators(owner).call() == [BASE_OWNER_COEFFICIENT + tokens, 0]
    base_coefficient += tokens
    tokens_supply += tokens

    assert pooling_contract.functions.baseCoefficient().call() == base_coefficient
    assert pooling_contract.functions.withdrawnTokens().call() == 0
    assert token.functions.balanceOf(pooling_contract.address).call() == tokens_supply

    events = deposit_log.get_all_entries()
    assert len(events) == len(delegators) + 1
    event_args = events[-1]['args']
    assert event_args['sender'] == owner
    assert event_args['value'] == tokens
    assert event_args['coefficient'] == BASE_OWNER_COEFFICIENT + tokens

    # Delegators deposit tokens to the pooling contract again
    for index, delegator in enumerate(delegators):
        tokens = token.functions.balanceOf(delegator).call()
        tx = token.functions.approve(pooling_contract.address, tokens).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)
        tx = pooling_contract.functions.depositTokens(tokens).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)
        assert pooling_contract.functions.delegators(delegator).call() == [2 * tokens, 0]
        base_coefficient += tokens
        tokens_supply += tokens
        assert pooling_contract.functions.baseCoefficient().call() == base_coefficient
        assert token.functions.balanceOf(pooling_contract.address).call() == tokens_supply

        events = deposit_log.get_all_entries()
        assert len(events) == len(delegators) + 1 + index + 1
        event_args = events[-1]['args']
        assert event_args['sender'] == delegator
        assert event_args['value'] == tokens
        assert event_args['coefficient'] == 2 * tokens

    assert pooling_contract.functions.withdrawnTokens().call() == 0

    # Only owner can deposit tokens to the staking escrow
    stake = tokens_supply
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pooling_contract_interface.functions.depositAsStaker(stake, 5).transact({'from': delegators[0]})
        testerchain.wait_for_receipt(tx)

    tx = pooling_contract_interface.functions.depositAsStaker(stake, 5).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert pooling_contract.functions.baseCoefficient().call() == base_coefficient
    assert token.functions.balanceOf(pooling_contract.address).call() == 0

    # Give some tokens as a reward
    reward = token_economics.minimum_allowed_locked
    tx = token.functions.approve(escrow.address, reward).transact()
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.deposit(pooling_contract.address, reward, 0).transact()
    testerchain.wait_for_receipt(tx)

    # Only owner can withdraw tokens from the staking escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pooling_contract_interface.functions.withdrawAsStaker(reward).transact({'from': delegators[0]})
        testerchain.wait_for_receipt(tx)

    withdrawn_stake = reward + token_economics.minimum_allowed_locked // 10
    tx = pooling_contract_interface.functions.withdrawAsStaker(withdrawn_stake).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert pooling_contract.functions.baseCoefficient().call() == base_coefficient
    assert token.functions.balanceOf(pooling_contract.address).call() == withdrawn_stake
    tokens_supply = withdrawn_stake
    withdrawn_tokens = 0

    # Each delegator can withdraw some portion of tokens
    for index, delegator in enumerate(delegators):
        coefficient = pooling_contract.functions.delegators(delegator).call()[0]
        max_portion = withdrawn_stake * coefficient // base_coefficient

        # Can't withdraw more than max allowed
        with pytest.raises((TransactionFailed, ValueError)):
            tx = pooling_contract.functions.withdrawTokens(max_portion + 1).transact({'from': delegator})
            testerchain.wait_for_receipt(tx)

        portion = max_portion // 2
        tx = pooling_contract.functions.withdrawTokens(portion).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)
        assert pooling_contract.functions.delegators(delegator).call() == [coefficient, portion]
        tokens_supply -= portion
        withdrawn_tokens += portion
        assert pooling_contract.functions.baseCoefficient().call() == base_coefficient
        assert token.functions.balanceOf(pooling_contract.address).call() == tokens_supply
        assert pooling_contract.functions.withdrawnTokens().call() == withdrawn_tokens

        events = withdraw_log.get_all_entries()
        assert len(events) == index + 1
        event_args = events[-1]['args']
        assert event_args['sender'] == delegator
        assert event_args['value'] == portion

    # Owner withdraws tokens as delegator
    owner_coefficient = pooling_contract.functions.delegators(owner).call()[0]
    owner_max_portion = withdrawn_stake * owner_coefficient // base_coefficient

    tx = pooling_contract.functions.withdrawTokens(owner_max_portion).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert pooling_contract.functions.delegators(owner).call() == [owner_coefficient, owner_max_portion]
    tokens_supply -= owner_max_portion
    withdrawn_tokens += owner_max_portion
    assert pooling_contract.functions.baseCoefficient().call() == base_coefficient
    assert token.functions.balanceOf(pooling_contract.address).call() == tokens_supply
    assert pooling_contract.functions.withdrawnTokens().call() == withdrawn_tokens

    events = withdraw_log.get_all_entries()
    assert len(events) == len(delegators) + 1
    event_args = events[-1]['args']
    assert event_args['sender'] == owner
    assert event_args['value'] == owner_max_portion

    # Can't withdraw more than max allowed
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pooling_contract.functions.withdrawTokens(1).transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    # Each delegator can withdraw rest of tokens
    for index, delegator in enumerate(delegators):
        coefficient = pooling_contract.functions.delegators(delegator).call()[0]
        max_portion = withdrawn_stake * coefficient // base_coefficient
        portion = max_portion // 2

        # Can't withdraw more than max allowed
        with pytest.raises((TransactionFailed, ValueError)):
            tx = pooling_contract.functions.withdrawTokens(portion + 1).transact({'from': delegator})
            testerchain.wait_for_receipt(tx)

        tx = pooling_contract.functions.withdrawTokens(portion).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)
        assert pooling_contract.functions.delegators(delegator).call() == [coefficient, 2 * portion]
        tokens_supply -= portion
        withdrawn_tokens += portion
        assert pooling_contract.functions.baseCoefficient().call() == base_coefficient
        assert token.functions.balanceOf(pooling_contract.address).call() == tokens_supply
        assert pooling_contract.functions.withdrawnTokens().call() == withdrawn_tokens

        events = withdraw_log.get_all_entries()
        assert len(events) == len(delegators) + 1 + index + 1
        event_args = events[-1]['args']
        assert event_args['sender'] == delegator
        assert event_args['value'] == portion

    # Transfer ownership
    delegator = delegators[0]
    coefficient, withdrawn_tokens = pooling_contract.functions.delegators(delegator).call()
    assert pooling_contract.functions.delegators(owner).call() == [owner_coefficient, owner_max_portion]
    tx = pooling_contract.functions.transferOwnership(delegator).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    coefficient += owner_coefficient
    withdrawn_tokens += owner_max_portion
    assert pooling_contract.functions.delegators(delegator).call() == [coefficient, withdrawn_tokens]
    assert pooling_contract.functions.delegators(owner).call() == [0, 0]
