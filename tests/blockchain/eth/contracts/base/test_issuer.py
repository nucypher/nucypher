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

from nucypher.blockchain.economics import BaseEconomics

INITIAL_SUPPLY = 10 ** 26
TOTAL_SUPPLY = 2 * 10 ** 36


@pytest.fixture()
def token(testerchain, deploy_contract):
    # Create an ERC20 token
    token, _ = deploy_contract('NuCypherToken', _totalSupplyOfTokens=TOTAL_SUPPLY)
    return token


@pytest.mark.slow
def test_issuer(testerchain, token, deploy_contract):
    economics = BaseEconomics(initial_supply=INITIAL_SUPPLY,
                              total_supply=TOTAL_SUPPLY,
                              staking_coefficient=10 ** 39,
                              locked_periods_coefficient=10 ** 4,
                              maximum_rewarded_periods=10 ** 4,
                              hours_per_period=1)
    locking_duration_coefficient_1 = economics.maximum_rewarded_periods
    locking_duration_coefficient_2 = 2 * economics.maximum_rewarded_periods
    first_phase_total_supply = INITIAL_SUPPLY + 1000
    max_first_phase_reward = (first_phase_total_supply - INITIAL_SUPPLY) // 3

    def calculate_first_phase_reward(locked, total_locked, locked_periods):
        return max_first_phase_reward * locked * \
               (locked_periods + locking_duration_coefficient_1) // \
               (total_locked * locking_duration_coefficient_2)

    def calculate_second_phase_reward(locked, total_locked, locked_periods):
        return (economics.erc20_reward_supply - INITIAL_SUPPLY) * locked * \
               (locked_periods + locking_duration_coefficient_1) // \
               (total_locked * economics.staking_coefficient)

    creator = testerchain.client.accounts[0]
    staker = testerchain.client.accounts[1]

    # Only token contract is allowed in Issuer constructor
    # TODO update base economics
    bad_args = dict(_token=staker,
                    _hoursPerPeriod=economics.hours_per_period,
                    _secondPhaseMintingCoefficient=economics.staking_coefficient // locking_duration_coefficient_2,
                    _lockingDurationCoefficient1=locking_duration_coefficient_1,
                    _lockingDurationCoefficient2=locking_duration_coefficient_2,
                    _maxRewardedPeriods=economics.maximum_rewarded_periods,
                    _firstPhaseTotalSupply=first_phase_total_supply,
                    _maxFirstPhaseReward=max_first_phase_reward)
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract(contract_name='IssuerMock', **bad_args)

    # Creator deploys the issuer
    args = bad_args
    args.update(_token=token.address)
    issuer, _ = deploy_contract(contract_name='IssuerMock', **args)
    events = issuer.events.Initialized.createFilter(fromBlock='latest')

    # Give staker tokens for reward and initialize contract
    tx = token.functions.approve(issuer.address, economics.erc20_reward_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Can't burn tokens before initialization
    with pytest.raises((TransactionFailed, ValueError)):
        tx = issuer.functions.burn(1).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Only owner can initialize
    with pytest.raises((TransactionFailed, ValueError)):
        tx = issuer.functions.initialize(0).transact({'from': staker})
        testerchain.wait_for_receipt(tx)
    tx = issuer.functions.initialize(economics.erc20_reward_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    events = events.get_all_entries()
    assert 1 == len(events)
    assert economics.erc20_reward_supply == events[0]['args']['reservedReward']
    balance = token.functions.balanceOf(issuer.address).call()

    # Can't initialize second time
    with pytest.raises((TransactionFailed, ValueError)):
        tx = issuer.functions.initialize(0).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # First phase

    # Check result of minting tokens
    tx = issuer.functions.testMint(0, 1000, 2000, 0).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    reward = calculate_first_phase_reward(1000, 2000, 0)
    assert calculate_second_phase_reward(1000, 2000, 0) != reward
    assert token.functions.balanceOf(staker).call() == reward
    assert token.functions.balanceOf(issuer.address).call() == balance - reward

    # The result must be more because of a different proportion of lockedValue and totalLockedValue
    tx = issuer.functions.testMint(0, 500, 500, 0).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    reward += calculate_first_phase_reward(500, 500, 0)
    assert token.functions.balanceOf(staker).call() == reward
    assert token.functions.balanceOf(issuer.address).call() == balance - reward

    # The result must be more because of bigger value of allLockedPeriods
    tx = issuer.functions.testMint(0, 500, 500, 10 ** 4).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    reward += calculate_first_phase_reward(500, 500, 10 ** 4)
    assert token.functions.balanceOf(staker).call() == reward
    assert token.functions.balanceOf(issuer.address).call() == balance - reward

    # The result is the same because allLockedPeriods more then specified coefficient _rewardedPeriods
    period = issuer.functions.getCurrentPeriod().call()
    tx = issuer.functions.testMint(period, 500, 500, 2 * 10 ** 4).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    reward += calculate_first_phase_reward(500, 500, 10 ** 4)
    assert token.functions.balanceOf(staker).call() == reward
    assert token.functions.balanceOf(issuer.address).call() == balance - reward

    # Still the first phase because minting period didn't change
    assert issuer.functions.previousPeriodSupply().call() + max_first_phase_reward < first_phase_total_supply
    assert issuer.functions.currentPeriodSupply().call() < first_phase_total_supply
    assert issuer.functions.currentPeriodSupply().call() + max_first_phase_reward >= first_phase_total_supply

    tx = issuer.functions.testMint(0, 100, 500, 10 ** 4).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    reward += calculate_first_phase_reward(100, 500, 10 ** 4)
    assert token.functions.balanceOf(staker).call() == reward
    assert token.functions.balanceOf(issuer.address).call() == balance - reward

    # Second phase
    assert issuer.functions.previousPeriodSupply().call() + max_first_phase_reward < first_phase_total_supply
    assert issuer.functions.currentPeriodSupply().call() < first_phase_total_supply
    assert issuer.functions.currentPeriodSupply().call() + max_first_phase_reward >= first_phase_total_supply

    # Check result of minting tokens
    tx = issuer.functions.testMint(period + 1, 1000, 2000, 0).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    current_reward = calculate_second_phase_reward(1000, 2000, 0)
    assert calculate_first_phase_reward(500, 500, 10 ** 4) != current_reward
    reward += current_reward
    assert reward == token.functions.balanceOf(staker).call()
    assert balance - reward == token.functions.balanceOf(issuer.address).call()

    # The result must be more because of a different proportion of lockedValue and totalLockedValue
    tx = issuer.functions.testMint(1, 500, 500, 0).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    reward += calculate_second_phase_reward(500, 500, 0)
    assert reward == token.functions.balanceOf(staker).call()
    assert balance - reward == token.functions.balanceOf(issuer.address).call()

    # The result must be more because of bigger value of allLockedPeriods
    tx = issuer.functions.testMint(1, 500, 500, 10 ** 4).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    reward += calculate_second_phase_reward(500, 500, 10 ** 4)
    assert reward == token.functions.balanceOf(staker).call()
    assert balance - reward == token.functions.balanceOf(issuer.address).call()

    # The result is the same because allLockedPeriods more then specified coefficient _rewardedPeriods
    tx = issuer.functions.testMint(1, 500, 500, 2 * 10 ** 4).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    reward += calculate_second_phase_reward(500, 500, 10 ** 4)
    assert reward == token.functions.balanceOf(staker).call()
    assert balance - reward == token.functions.balanceOf(issuer.address).call()


@pytest.mark.slow
def test_issuance_first_phase(testerchain, token, deploy_contract):
    """
    Checks stable issuance in the first phase
    """

    economics = BaseEconomics(initial_supply=INITIAL_SUPPLY,
                              total_supply=TOTAL_SUPPLY,
                              staking_coefficient=2 * 10 ** 35,
                              locked_periods_coefficient=1,
                              maximum_rewarded_periods=1,
                              hours_per_period=1)

    creator = testerchain.client.accounts[0]
    staker = testerchain.client.accounts[1]

    # Creator deploys the contract
    # TODO update base economics
    first_phase_total_supply = INITIAL_SUPPLY + 1000
    max_first_phase_reward = (first_phase_total_supply - INITIAL_SUPPLY) // 5
    args = dict(_token=token.address,
                _hoursPerPeriod=economics.hours_per_period,
                _secondPhaseMintingCoefficient=economics.staking_coefficient // (
                            2 * economics.maximum_rewarded_periods),
                _lockingDurationCoefficient1=economics.maximum_rewarded_periods,
                _lockingDurationCoefficient2=2 * economics.maximum_rewarded_periods,
                _maxRewardedPeriods=economics.maximum_rewarded_periods,
                _firstPhaseTotalSupply=first_phase_total_supply,
                _maxFirstPhaseReward=max_first_phase_reward)
    issuer, _ = deploy_contract(contract_name='IssuerMock', **args)

    # Give staker tokens for reward and initialize contract
    tx = token.functions.approve(issuer.address, economics.erc20_reward_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = issuer.functions.initialize(economics.erc20_reward_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    reward = issuer.functions.getReservedReward().call()

    # Mint some tokens and save result of minting
    period = issuer.functions.getCurrentPeriod().call()
    tx = issuer.functions.testMint(period + 1, 1, 1, economics.maximum_rewarded_periods).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    one_period = token.functions.balanceOf(staker).call()
    assert one_period == max_first_phase_reward

    # Inflation rate must be the same in all periods of the first phase
    # Mint more tokens in the same period
    tx = issuer.functions.testMint(period + 1, 1, 1, economics.maximum_rewarded_periods).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert 2 * one_period == token.functions.balanceOf(staker).call()
    assert reward - token.functions.balanceOf(staker).call() == issuer.functions.getReservedReward().call()

    # Mint tokens in the next period
    tx = issuer.functions.testMint(period + 2, 1, 1, economics.maximum_rewarded_periods).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert 3 * one_period == token.functions.balanceOf(staker).call()
    assert reward - token.functions.balanceOf(staker).call() == issuer.functions.getReservedReward().call()

    # Mint tokens in the first period again
    tx = issuer.functions.testMint(period + 1, 1, 1, economics.maximum_rewarded_periods).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert 4 * one_period == token.functions.balanceOf(staker).call()
    assert reward - token.functions.balanceOf(staker).call() == issuer.functions.getReservedReward().call()

    # Mint tokens in the next period
    tx = issuer.functions.testMint(period + 3, 1, 1, economics.maximum_rewarded_periods).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert 5 * one_period == token.functions.balanceOf(staker).call()
    assert reward - token.functions.balanceOf(staker).call() == issuer.functions.getReservedReward().call()

    # Switch to the second phase
    assert issuer.functions.previousPeriodSupply().call() < first_phase_total_supply
    assert issuer.functions.currentPeriodSupply().call() == first_phase_total_supply

    tx = issuer.functions.testMint(period + 4, 1, 1, economics.maximum_rewarded_periods).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert 6 * one_period > token.functions.balanceOf(staker).call()
    assert reward - token.functions.balanceOf(staker).call() == issuer.functions.getReservedReward().call()
    minted_amount_second_phase = token.functions.balanceOf(staker).call() - 5 * one_period

    # Return some tokens as a reward
    # balance = token.functions.balanceOf(staker).call() TODO
    reward = issuer.functions.getReservedReward().call()
    amount_to_burn = 4 * one_period + minted_amount_second_phase
    tx = token.functions.approve(issuer.address, amount_to_burn).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    tx = issuer.functions.burn(amount_to_burn).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert reward + amount_to_burn == issuer.functions.getReservedReward().call()
    assert one_period == token.functions.balanceOf(staker).call()

    events = issuer.events.Burnt.createFilter(fromBlock=0).get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert staker == event_args['sender']
    assert amount_to_burn == event_args['value']

    # Switch back to the first phase
    reward += amount_to_burn
    tx = issuer.functions.testMint(period + 5, 1, 1, economics.maximum_rewarded_periods).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert 2 * one_period == token.functions.balanceOf(staker).call()
    assert reward - one_period == issuer.functions.getReservedReward().call()


@pytest.mark.slow
def test_issuance_second_phase(testerchain, token, deploy_contract):
    """
    Check for decreasing of issuance after minting in the second phase.
    During one period inflation rate must be the same
    """

    economics = BaseEconomics(initial_supply=INITIAL_SUPPLY,
                              total_supply=TOTAL_SUPPLY,
                              staking_coefficient=2 * 10 ** 15,
                              locked_periods_coefficient=1,
                              maximum_rewarded_periods=1,
                              hours_per_period=1)

    creator = testerchain.client.accounts[0]
    staker = testerchain.client.accounts[1]

    # Creator deploys the contract
    # TODO update base economics
    args = dict(_token=token.address,
                _hoursPerPeriod=economics.hours_per_period,
                _secondPhaseMintingCoefficient=economics.staking_coefficient // (
                            2 * economics.maximum_rewarded_periods),
                _lockingDurationCoefficient1=economics.maximum_rewarded_periods,
                _lockingDurationCoefficient2=2 * economics.maximum_rewarded_periods,
                _maxRewardedPeriods=economics.maximum_rewarded_periods,
                _firstPhaseTotalSupply=0,
                _maxFirstPhaseReward=0)
    issuer, _ = deploy_contract(contract_name='IssuerMock', **args)

    # Give staker tokens for reward and initialize contract
    tx = token.functions.approve(issuer.address, economics.erc20_reward_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = issuer.functions.initialize(economics.erc20_reward_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    reward = issuer.functions.getReservedReward().call()

    # Mint some tokens and save result of minting
    period = issuer.functions.getCurrentPeriod().call()
    tx = issuer.functions.testMint(period + 1, 1, 1, 0).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    one_period = token.functions.balanceOf(staker).call()

    # Mint more tokens in the same period, inflation rate must be the same as in previous minting
    tx = issuer.functions.testMint(period + 1, 1, 1, 0).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert 2 * one_period == token.functions.balanceOf(staker).call()
    assert reward - token.functions.balanceOf(staker).call() == issuer.functions.getReservedReward().call()

    # Mint tokens in the next period, inflation rate must be lower than in previous minting
    tx = issuer.functions.testMint(period + 2, 1, 1, 0).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert 3 * one_period > token.functions.balanceOf(staker).call()
    assert reward - token.functions.balanceOf(staker).call() == issuer.functions.getReservedReward().call()
    minted_amount = token.functions.balanceOf(staker).call() - 2 * one_period

    # Mint tokens in the first period again, inflation rate must be the same as in previous minting
    # but can't be equals as in first minting because rate can't be increased
    tx = issuer.functions.testMint(period + 1, 1, 1, 0).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert 2 * one_period + 2 * minted_amount == token.functions.balanceOf(staker).call()
    assert reward - token.functions.balanceOf(staker).call() == issuer.functions.getReservedReward().call()

    # Mint tokens in the next period, inflation rate must be lower than in previous minting
    tx = issuer.functions.testMint(period + 3, 1, 1, 0).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert 2 * one_period + 3 * minted_amount > token.functions.balanceOf(staker).call()
    assert reward - token.functions.balanceOf(staker).call() == issuer.functions.getReservedReward().call()

    # Return some tokens as a reward
    balance = token.functions.balanceOf(staker).call()
    reward = issuer.functions.getReservedReward().call()
    amount_to_burn = 2 * one_period + 2 * minted_amount
    tx = token.functions.transfer(staker, amount_to_burn).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(issuer.address, amount_to_burn).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    tx = issuer.functions.burn(amount_to_burn).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert reward + amount_to_burn == issuer.functions.getReservedReward().call()

    events = issuer.events.Burnt.createFilter(fromBlock=0).get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert staker == event_args['sender']
    assert amount_to_burn == event_args['value']

    # Rate will be increased because some tokens were returned
    tx = issuer.functions.testMint(period + 3, 1, 1, 0).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert balance + one_period == token.functions.balanceOf(staker).call()
    assert reward + one_period + 2 * minted_amount == issuer.functions.getReservedReward().call()


@pytest.mark.slow
def test_upgrading(testerchain, token, deploy_contract):
    creator = testerchain.client.accounts[0]

    # Deploy contract
    contract_library_v1, _ = deploy_contract(
        contract_name='IssuerMock',
        _token=token.address,
        _hoursPerPeriod=1,
        _secondPhaseMintingCoefficient=1,
        _lockingDurationCoefficient1=1,
        _lockingDurationCoefficient2=2,
        _maxRewardedPeriods=1,
        _firstPhaseTotalSupply=1,
        _maxFirstPhaseReward=1
    )
    dispatcher, _ = deploy_contract('Dispatcher', contract_library_v1.address)

    # Deploy second version of the contract
    contract_library_v2, _ = deploy_contract(
        contract_name='IssuerV2Mock',
        _token=token.address,
        _hoursPerPeriod=2,
        _secondPhaseMintingCoefficient=2,
        _lockingDurationCoefficient1=2,
        _lockingDurationCoefficient2=4,
        _maxRewardedPeriods=2,
        _firstPhaseTotalSupply=2,
        _maxFirstPhaseReward=2
    )
    contract = testerchain.client.get_contract(
        abi=contract_library_v2.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Can't call `finishUpgrade` and `verifyState` methods outside upgrade lifecycle
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract_library_v1.functions.finishUpgrade(contract.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract_library_v1.functions.verifyState(contract.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Give tokens for reward and initialize contract
    tx = token.functions.approve(contract.address, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.initialize(10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Upgrade to the second version, check new and old values of variables
    period = contract.functions.currentMintingPeriod().call()
    assert 2 == contract.functions.mintingCoefficient().call()
    tx = dispatcher.functions.upgrade(contract_library_v2.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert contract_library_v2.address == dispatcher.functions.target().call()
    assert 8 == contract.functions.mintingCoefficient().call()
    assert 2 * 3600 == contract.functions.secondsPerPeriod().call()
    assert 2 == contract.functions.lockingDurationCoefficient1().call()
    assert 4 == contract.functions.lockingDurationCoefficient2().call()
    assert 2 == contract.functions.maxRewardedPeriods().call()
    assert 2 == contract.functions.firstPhaseTotalSupply().call()
    assert 2 == contract.functions.maxFirstPhaseReward().call()
    assert period == contract.functions.currentMintingPeriod().call()
    assert TOTAL_SUPPLY == contract.functions.totalSupply().call()
    # Check method from new ABI
    tx = contract.functions.setValueToCheck(3).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 3 == contract.functions.valueToCheck().call()

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad, _ = deploy_contract(
        contract_name='IssuerBad',
        _token=token.address,
        _hoursPerPeriod=2,
        _miningCoefficient=4,
        _lockedPeriodsCoefficient=2,
        _rewardedPeriods=2
    )
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_v1.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # But can rollback
    tx = dispatcher.functions.rollback().transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    # Check old values
    assert contract_library_v1.address == dispatcher.functions.target().call()
    assert 2 == contract.functions.mintingCoefficient().call()
    assert 3600 == contract.functions.secondsPerPeriod().call()
    assert 1 == contract.functions.lockingDurationCoefficient1().call()
    assert 2 == contract.functions.lockingDurationCoefficient2().call()
    assert 1 == contract.functions.maxRewardedPeriods().call()
    assert 1 == contract.functions.firstPhaseTotalSupply().call()
    assert 1 == contract.functions.maxFirstPhaseReward().call()
    assert period == contract.functions.currentMintingPeriod().call()
    assert TOTAL_SUPPLY == contract.functions.totalSupply().call()
    # After rollback can't use new ABI
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract.functions.setValueToCheck(2).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Try to upgrade to the bad version again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    events = dispatcher.events.StateVerified.createFilter(fromBlock=0).get_all_entries()
    assert 4 == len(events)
    event_args = events[0]['args']
    assert contract_library_v1.address == event_args['testTarget']
    assert creator == event_args['sender']
    event_args = events[1]['args']
    assert contract_library_v2.address == event_args['testTarget']
    assert creator == event_args['sender']
    assert event_args == events[2]['args']
    event_args = events[3]['args']
    assert contract_library_v2.address == event_args['testTarget']
    assert creator == event_args['sender']

    events = dispatcher.events.UpgradeFinished.createFilter(fromBlock=0).get_all_entries()
    assert 3 == len(events)
    event_args = events[0]['args']
    assert contract_library_v1.address == event_args['target']
    assert creator == event_args['sender']
    event_args = events[1]['args']
    assert contract_library_v2.address == event_args['target']
    assert creator == event_args['sender']
    event_args = events[2]['args']
    assert contract_library_v1.address == event_args['target']
    assert creator == event_args['sender']
