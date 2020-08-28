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
from web3 import Web3
from web3.contract import Contract

from nucypher.blockchain.eth.token import NU


OWNER_FRACTION = int(NU.from_tokens(100_000))


@pytest.fixture()
def pooling_contract(testerchain, router, deploy_contract):
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]

    contract, _ = deploy_contract('PoolingStakingContract', router.address, OWNER_FRACTION)

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


def test_staking(testerchain, token_economics, token, escrow, pooling_contract, pooling_contract_interface):
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]
    delegators = testerchain.client.accounts[2:5]
    deposit_log = pooling_contract.events.TokensDeposited.createFilter(fromBlock='latest')
    withdraw_log = pooling_contract.events.TokensWithdrawn.createFilter(fromBlock='latest')

    assert pooling_contract.functions.ownerFraction().call() == OWNER_FRACTION
    assert pooling_contract.functions.ownerWithdrawnReward().call() == 0
    assert pooling_contract.functions.totalDepositedTokens().call() == 0
    assert pooling_contract.functions.totalWithdrawnReward().call() == 0
    assert token.functions.balanceOf(pooling_contract.address).call() == 0
    assert pooling_contract.functions.getAvailableOwnerReward().call() == 0
    assert pooling_contract.functions.getAvailableReward().call() == 0

    # Give some tokens to delegators
    for index, delegator in enumerate(delegators):
        tokens = token_economics.minimum_allowed_locked // (index + 1) * 2
        tx = token.functions.transfer(delegator, tokens).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Delegators deposit tokens to the pooling contract
    total_deposited_tokens = 0
    tokens_supply = 0
    assert pooling_contract.functions.getAvailableReward().call() == 0
    for index, delegator in enumerate(delegators):
        assert pooling_contract.functions.delegators(delegator).call() == [0, 0, 0]
        assert pooling_contract.functions.getAvailableReward(delegator).call() == 0
        tokens = token.functions.balanceOf(delegator).call() // 2
        tx = token.functions.approve(pooling_contract.address, tokens).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)
        tx = pooling_contract.functions.depositTokens(tokens).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)
        assert pooling_contract.functions.delegators(delegator).call() == [tokens, 0, 0]
        assert pooling_contract.functions.getAvailableReward(delegator).call() == 0
        total_deposited_tokens += tokens
        tokens_supply += tokens
        assert pooling_contract.functions.totalDepositedTokens().call() == total_deposited_tokens
        assert token.functions.balanceOf(pooling_contract.address).call() == tokens_supply

        events = deposit_log.get_all_entries()
        assert len(events) == index + 1
        event_args = events[-1]['args']
        assert event_args['sender'] == delegator
        assert event_args['value'] == tokens
        assert event_args['depositedTokens'] == tokens

    assert pooling_contract.functions.ownerFraction().call() == OWNER_FRACTION
    assert pooling_contract.functions.ownerWithdrawnReward().call() == 0
    assert pooling_contract.functions.totalWithdrawnReward().call() == 0
    assert pooling_contract.functions.getAvailableOwnerReward().call() == 0
    assert pooling_contract.functions.getAvailableReward().call() == 0

    # Disable deposit
    log = pooling_contract.events.DepositSet.createFilter(fromBlock='latest')
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pooling_contract.functions.disableDeposit().transact({'from': delegators[0]})
        testerchain.wait_for_receipt(tx)
    tx = pooling_contract.functions.disableDeposit().transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    events = log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['sender'] == owner
    assert not event_args['value']

    delegator = delegators[0]
    tokens = token.functions.balanceOf(delegator).call()
    tx = token.functions.approve(pooling_contract.address, tokens).transact({'from': delegator})
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pooling_contract.functions.depositTokens(tokens).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(pooling_contract.address, 0).transact({'from': delegator})
    testerchain.wait_for_receipt(tx)

    # Enable deposit
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pooling_contract.functions.enableDeposit().transact({'from': delegators[0]})
        testerchain.wait_for_receipt(tx)
    tx = pooling_contract.functions.enableDeposit().transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    events = log.get_all_entries()
    assert len(events) == 2
    event_args = events[-1]['args']
    assert event_args['sender'] == owner
    assert event_args['value']

    # Delegators deposit tokens to the pooling contract again
    for index, delegator in enumerate(delegators):
        tokens = token.functions.balanceOf(delegator).call()
        tx = token.functions.approve(pooling_contract.address, tokens).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)
        tx = pooling_contract.functions.depositTokens(tokens).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)
        assert pooling_contract.functions.delegators(delegator).call() == [2 * tokens, 0, 0]
        total_deposited_tokens += tokens
        tokens_supply += tokens
        assert pooling_contract.functions.totalDepositedTokens().call() == total_deposited_tokens
        assert token.functions.balanceOf(pooling_contract.address).call() == tokens_supply

        events = deposit_log.get_all_entries()
        assert len(events) == len(delegators) + index + 1
        event_args = events[-1]['args']
        assert event_args['sender'] == delegator
        assert event_args['value'] == tokens
        assert event_args['depositedTokens'] == 2 * tokens

    assert pooling_contract.functions.totalWithdrawnReward().call() == 0

    # Only owner can deposit tokens to the staking escrow
    stake = tokens_supply
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pooling_contract_interface.functions.depositAsStaker(stake, 5).transact({'from': delegators[0]})
        testerchain.wait_for_receipt(tx)

    tx = pooling_contract_interface.functions.depositAsStaker(stake, 5).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert pooling_contract.functions.totalDepositedTokens().call() == total_deposited_tokens
    assert token.functions.balanceOf(pooling_contract.address).call() == 0

    # Give some tokens as a reward
    assert pooling_contract.functions.getAvailableReward().call() == 0
    reward = token_economics.minimum_allowed_locked
    tx = token.functions.approve(escrow.address, reward).transact()
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.deposit(pooling_contract.address, reward, 0).transact()
    testerchain.wait_for_receipt(tx)

    # Only owner can withdraw tokens from the staking escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pooling_contract_interface.functions.withdrawAsStaker(reward).transact({'from': delegators[0]})
        testerchain.wait_for_receipt(tx)

    withdrawn_stake = reward + stake // 2
    assert pooling_contract.functions.getAvailableReward().call() == 0
    tx = pooling_contract_interface.functions.withdrawAsStaker(withdrawn_stake).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert pooling_contract.functions.getAvailableReward().call() == reward
    owner_reward = reward * OWNER_FRACTION // (total_deposited_tokens + OWNER_FRACTION)
    assert pooling_contract.functions.getAvailableOwnerReward().call() == owner_reward
    assert pooling_contract.functions.totalDepositedTokens().call() == total_deposited_tokens
    assert token.functions.balanceOf(pooling_contract.address).call() == withdrawn_stake
    tokens_supply = withdrawn_stake
    withdrawn_tokens = 0

    # Each delegator can withdraw some portion of tokens
    available_reward = reward
    for index, delegator in enumerate(delegators):
        deposited_tokens = pooling_contract.functions.delegators(delegator).call()[0]
        max_portion = reward * deposited_tokens // (total_deposited_tokens + OWNER_FRACTION)

        # Can't withdraw more than max allowed
        with pytest.raises((TransactionFailed, ValueError)):
            tx = pooling_contract.functions.withdrawTokens(max_portion + deposited_tokens + 1).transact({'from': delegator})
            testerchain.wait_for_receipt(tx)

        portion = max_portion // 2
        assert pooling_contract.functions.getAvailableReward(delegator).call() == max_portion
        tx = pooling_contract.functions.withdrawTokens(portion).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)
        assert pooling_contract.functions.delegators(delegator).call() == [deposited_tokens, portion, 0]
        assert pooling_contract.functions.getAvailableReward(delegator).call() == max_portion - portion
        tokens_supply -= portion
        withdrawn_tokens += portion
        available_reward -= portion
        assert pooling_contract.functions.totalDepositedTokens().call() == total_deposited_tokens
        assert token.functions.balanceOf(pooling_contract.address).call() == tokens_supply
        assert token.functions.balanceOf(delegator).call() == portion
        assert pooling_contract.functions.totalWithdrawnReward().call() == withdrawn_tokens

        events = withdraw_log.get_all_entries()
        assert len(events) == index + 1
        event_args = events[-1]['args']
        assert event_args['sender'] == delegator
        assert event_args['value'] == portion
        assert event_args['depositedTokens'] == deposited_tokens

    # Owner withdraws tokens
    assert pooling_contract.functions.getAvailableOwnerReward().call() == owner_reward
    assert pooling_contract.functions.getAvailableReward().call() == available_reward

    # Only owner can call this method
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pooling_contract.functions.withdrawOwnerReward().transact({'from': delegators[0]})
        testerchain.wait_for_receipt(tx)

    tx = pooling_contract.functions.withdrawOwnerReward().transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert pooling_contract.functions.ownerFraction().call() == OWNER_FRACTION
    assert pooling_contract.functions.ownerWithdrawnReward().call() == owner_reward
    assert pooling_contract.functions.getAvailableOwnerReward().call() == 0
    tokens_supply -= owner_reward
    withdrawn_tokens += owner_reward
    assert pooling_contract.functions.totalDepositedTokens().call() == total_deposited_tokens
    assert token.functions.balanceOf(pooling_contract.address).call() == tokens_supply
    assert token.functions.balanceOf(owner).call() == owner_reward
    assert pooling_contract.functions.totalWithdrawnReward().call() == withdrawn_tokens
    assert pooling_contract.functions.getAvailableReward().call() == available_reward - owner_reward

    events = withdraw_log.get_all_entries()
    assert len(events) == len(delegators) + 1
    event_args = events[-1]['args']
    assert event_args['sender'] == owner
    assert event_args['value'] == owner_reward
    assert event_args['depositedTokens'] == 0

    # Can't withdraw more than max allowed
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pooling_contract.functions.withdrawOwnerReward().transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    # TODO test same case with checking withdrawnETH
    # Each delegator can withdraw rest of reward and some portion of deposit
    previous_total_deposited_tokens = total_deposited_tokens
    for index, delegator in enumerate(delegators):
        deposited_tokens = pooling_contract.functions.delegators(delegator).call()[0]
        max_portion = reward * deposited_tokens // (previous_total_deposited_tokens + OWNER_FRACTION)
        supposed_portion = max_portion // 2
        reward_portion = pooling_contract.functions.getAvailableReward(delegator).call()
        # could be some rounding errors
        assert abs(supposed_portion - reward_portion) <= 1

        # Can't withdraw more than max allowed
        with pytest.raises((TransactionFailed, ValueError)):
            tx = pooling_contract.functions.withdrawTokens(reward_portion + deposited_tokens + 1).transact({'from': delegator})
            testerchain.wait_for_receipt(tx)

        deposit_to_withdraw = deposited_tokens // 2
        portion = reward_portion + deposit_to_withdraw
        previous_portion = token.functions.balanceOf(delegator).call()
        tx = pooling_contract.functions.withdrawTokens(portion).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)
        assert pooling_contract.functions.delegators(delegator).call() == \
               [deposited_tokens - deposit_to_withdraw, max_portion - reward_portion, 0]
        tokens_supply -= portion
        # withdrawn_tokens += reward_portion
        total_deposited_tokens -= deposit_to_withdraw
        assert pooling_contract.functions.totalDepositedTokens().call() == total_deposited_tokens
        assert token.functions.balanceOf(pooling_contract.address).call() == tokens_supply
        assert token.functions.balanceOf(delegator).call() == previous_portion + reward_portion + deposit_to_withdraw
        assert pooling_contract.functions.totalWithdrawnReward().call() == withdrawn_tokens
        assert pooling_contract.functions.getAvailableReward(delegator).call() == 0

        events = withdraw_log.get_all_entries()
        assert len(events) == len(delegators) + 1 + index + 1
        event_args = events[-1]['args']
        assert event_args['sender'] == delegator
        assert event_args['value'] == portion
        assert event_args['depositedTokens'] == deposited_tokens - deposit_to_withdraw

    # could be some rounding errors
    assert pooling_contract.functions.getAvailableReward().call() <= 10


def test_fee(testerchain, token_economics, token, policy_manager, pooling_contract, pooling_contract_interface):
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]
    delegators = testerchain.client.accounts[2:5]
    withdraw_log = pooling_contract.events.ETHWithdrawn.createFilter(fromBlock='latest')

    assert pooling_contract.functions.ownerFraction().call() == OWNER_FRACTION
    assert pooling_contract.functions.ownerWithdrawnETH().call() == 0
    assert pooling_contract.functions.totalDepositedTokens().call() == 0
    assert pooling_contract.functions.totalWithdrawnETH().call() == 0
    assert pooling_contract.functions.delegators(owner).call() == [0, 0, 0]
    assert token.functions.balanceOf(pooling_contract.address).call() == 0
    assert pooling_contract.functions.getAvailableOwnerETH().call() == 0

    # Give some tokens to delegators and deposit them
    for index, delegator in enumerate(delegators):
        tokens = token_economics.minimum_allowed_locked // (index + 1)
        tx = token.functions.transfer(delegator, tokens).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
        tx = token.functions.approve(pooling_contract.address, tokens).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)
        tx = pooling_contract.functions.depositTokens(tokens).transact({'from': delegator})
        testerchain.wait_for_receipt(tx)

    total_deposited_tokens = pooling_contract.functions.totalDepositedTokens().call()
    assert pooling_contract.functions.totalWithdrawnETH().call() == 0
    assert testerchain.client.get_balance(pooling_contract.address) == 0

    # Give some fees
    value = Web3.toWei(1, 'ether')
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': policy_manager.address, 'value': value})
    testerchain.wait_for_receipt(tx)

    # Only owner can withdraw fees from the policy manager
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pooling_contract_interface.functions.withdrawPolicyFee().transact({'from': delegators[0]})
        testerchain.wait_for_receipt(tx)

    balance = testerchain.client.get_balance(owner)
    tx = pooling_contract_interface.functions.withdrawPolicyFee().transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert testerchain.client.get_balance(pooling_contract.address) == value
    assert testerchain.client.get_balance(owner) == balance
    assert pooling_contract.functions.totalDepositedTokens().call() == total_deposited_tokens
    withdrawn_eth = 0
    eth_supply = value

    # Each delegator can withdraw portion of eth
    for index, delegator in enumerate(delegators):
        deposited_tokens = pooling_contract.functions.delegators(delegator).call()[0]
        max_portion = value * deposited_tokens // (total_deposited_tokens + OWNER_FRACTION)
        balance = testerchain.client.get_balance(delegator)
        assert pooling_contract.functions.getAvailableETH(delegator).call() == max_portion

        tx = pooling_contract.functions.withdrawETH().transact({'from': delegator, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
        assert pooling_contract.functions.delegators(delegator).call() == [deposited_tokens, 0, max_portion]
        eth_supply -= max_portion
        withdrawn_eth += max_portion
        assert pooling_contract.functions.totalDepositedTokens().call() == total_deposited_tokens
        assert testerchain.client.get_balance(pooling_contract.address) == eth_supply
        assert testerchain.client.get_balance(delegator) == balance + max_portion
        assert pooling_contract.functions.totalWithdrawnETH().call() == withdrawn_eth

        # Can't withdraw more than max allowed
        with pytest.raises((TransactionFailed, ValueError)):
            tx = pooling_contract.functions.withdrawETH().transact({'from': delegator})
            testerchain.wait_for_receipt(tx)

        events = withdraw_log.get_all_entries()
        assert len(events) == index + 1
        event_args = events[-1]['args']
        assert event_args['sender'] == delegator
        assert event_args['value'] == max_portion

    # Owner withdraws tokens
    owner_portion = value * OWNER_FRACTION // (total_deposited_tokens + OWNER_FRACTION)
    assert pooling_contract.functions.getAvailableOwnerETH().call() == owner_portion

    balance = testerchain.client.get_balance(owner)
    tx = pooling_contract.functions.withdrawOwnerETH().transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert pooling_contract.functions.getAvailableOwnerETH().call() == 0
    eth_supply -= owner_portion
    withdrawn_eth += owner_portion
    assert pooling_contract.functions.totalDepositedTokens().call() == total_deposited_tokens
    assert testerchain.client.get_balance(pooling_contract.address) == eth_supply
    assert testerchain.client.get_balance(owner) == balance + owner_portion
    assert pooling_contract.functions.totalWithdrawnETH().call() == withdrawn_eth

    events = withdraw_log.get_all_entries()
    assert len(events) == len(delegators) + 1
    event_args = events[-1]['args']
    assert event_args['sender'] == owner
    assert event_args['value'] == owner_portion

    # Can't withdraw more than max allowed
    with pytest.raises((TransactionFailed, ValueError)):
        tx = pooling_contract.functions.withdrawOwnerETH().transact({'from': owner, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)


def test_reentrancy(testerchain, pooling_contract, token, deploy_contract):
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]

    # Prepare contracts
    reentrancy_contract, _ = deploy_contract('ReentrancyTest')
    contract_address = reentrancy_contract.address
    tx = pooling_contract.functions.transferOwnership(contract_address).transact({'from': owner})
    testerchain.wait_for_receipt(tx)

    # Transfer ETH to the contract
    value = Web3.toWei(1, 'ether')
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': pooling_contract.address, 'value': value})
    testerchain.wait_for_receipt(tx)
    assert testerchain.client.get_balance(pooling_contract.address) == value

    # Change eth distribution, owner will be able to withdraw only half
    tokens = OWNER_FRACTION
    tx = token.functions.transfer(owner, tokens).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(pooling_contract.address, tokens).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    tx = pooling_contract.functions.depositTokens(tokens).transact({'from': owner})
    testerchain.wait_for_receipt(tx)

    # Try to withdraw ETH twice
    balance = testerchain.w3.eth.getBalance(contract_address)
    transaction = pooling_contract.functions.withdrawETH().buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(2, transaction['to'], 0, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction({'to': contract_address})
        testerchain.wait_for_receipt(tx)
    assert testerchain.w3.eth.getBalance(contract_address) == balance

    # TODO reentrancy test for owner
