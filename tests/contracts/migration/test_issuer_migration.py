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


def test_issuer_migration(testerchain, token, token_economics, deploy_contract):
    creator = testerchain.client.accounts[0]

    # Deploy old contract
    issuer_old_library, _ = deploy_contract(
        contract_name='IssuerOldMock',
        _token=token.address,
        _hoursPerPeriod=token_economics.genesis_hours_per_period,
        _issuanceDecayCoefficient=int(token_economics.issuance_decay_coefficient),
        _lockDurationCoefficient1=int(token_economics.lock_duration_coefficient_1),
        _lockDurationCoefficient2=int(token_economics.lock_duration_coefficient_2),
        _maximumRewardedPeriods=token_economics.maximum_rewarded_periods,
        _firstPhaseTotalSupply=int(token_economics.first_phase_total_supply),
        _firstPhaseMaxIssuance=int(token_economics.first_phase_max_issuance)
    )
    dispatcher, _ = deploy_contract('Dispatcher', issuer_old_library.address)

    contract = testerchain.client.get_contract(
        abi=issuer_old_library.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    assert contract.functions.secondsPerPeriod().call() == token_economics.genesis_seconds_per_period

    current_period = contract.functions.getCurrentPeriod().call()
    testerchain.time_travel(hours=token_economics.genesis_hours_per_period)
    assert contract.functions.getCurrentPeriod().call() == current_period + 1
    current_period = contract.functions.getCurrentPeriod().call()
    current_minting_period = current_period

    # Give tokens for reward and initialize contract
    assert contract.functions.currentMintingPeriod().call() == 0
    tx = token.functions.approve(contract.address, token_economics.erc20_reward_supply).transact()
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.initialize(token_economics.erc20_reward_supply, creator).transact()
    testerchain.wait_for_receipt(tx)
    assert contract.functions.currentMintingPeriod().call() == current_minting_period

    # We can only extend period
    with pytest.raises((TransactionFailed, ValueError)):
        deploy_contract(
            contract_name='IssuerMock',
            _token=token.address,
            _genesisHoursPerPeriod=token_economics.hours_per_period,
            _hoursPerPeriod=token_economics.genesis_hours_per_period,
            _issuanceDecayCoefficient=int(token_economics.issuance_decay_coefficient),
            _lockDurationCoefficient1=int(token_economics.lock_duration_coefficient_1),
            _lockDurationCoefficient2=int(token_economics.lock_duration_coefficient_2),
            _maximumRewardedPeriods=token_economics.maximum_rewarded_periods,
            _firstPhaseTotalSupply=int(token_economics.first_phase_total_supply),
            _firstPhaseMaxIssuance=int(token_economics.first_phase_max_issuance)
        )

    # Deploy new version of the contract
    issuer_library, _ = deploy_contract(
        contract_name='IssuerMock',
        _token=token.address,
        _genesisHoursPerPeriod=token_economics.genesis_hours_per_period,
        _hoursPerPeriod=token_economics.hours_per_period,
        _issuanceDecayCoefficient=int(token_economics.issuance_decay_coefficient),
        _lockDurationCoefficient1=int(token_economics.lock_duration_coefficient_1),
        _lockDurationCoefficient2=int(token_economics.lock_duration_coefficient_2),
        _maximumRewardedPeriods=token_economics.maximum_rewarded_periods,
        _firstPhaseTotalSupply=int(token_economics.first_phase_total_supply),
        _firstPhaseMaxIssuance=int(token_economics.first_phase_max_issuance)
    )
    contract = testerchain.client.get_contract(
        abi=issuer_library.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    tx = dispatcher.functions.upgrade(issuer_library.address).transact()
    testerchain.wait_for_receipt(tx)
    assert contract.functions.secondsPerPeriod().call() == token_economics.seconds_per_period
    assert contract.functions.genesisSecondsPerPeriod().call() == token_economics.genesis_seconds_per_period
    assert contract.functions.getCurrentPeriod().call() == current_period // 2
    assert contract.functions.currentMintingPeriod().call() == current_minting_period // 2

    tx = dispatcher.functions.upgrade(issuer_library.address).transact()
    testerchain.wait_for_receipt(tx)
    assert contract.functions.currentMintingPeriod().call() == current_minting_period // 2

    testerchain.time_travel(periods=1, periods_base=token_economics.seconds_per_period)
    current_period = contract.functions.getCurrentPeriod().call()
    testerchain.time_travel(hours=token_economics.genesis_hours_per_period)
    assert contract.functions.getCurrentPeriod().call() == current_period
    testerchain.time_travel(hours=token_economics.genesis_hours_per_period)
    assert contract.functions.getCurrentPeriod().call() == current_period + 1
    testerchain.time_travel(hours=token_economics.hours_per_period)
    assert contract.functions.getCurrentPeriod().call() == current_period + 2
    assert contract.functions.currentMintingPeriod().call() == current_minting_period // 2

    # Deploy again
    issuer_library_2, _ = deploy_contract(
        contract_name='IssuerMock',
        _token=token.address,
        _genesisHoursPerPeriod=token_economics.hours_per_period,
        _hoursPerPeriod=2 * token_economics.hours_per_period,
        _issuanceDecayCoefficient=int(token_economics.issuance_decay_coefficient),
        _lockDurationCoefficient1=int(token_economics.lock_duration_coefficient_1),
        _lockDurationCoefficient2=int(token_economics.lock_duration_coefficient_2),
        _maximumRewardedPeriods=token_economics.maximum_rewarded_periods,
        _firstPhaseTotalSupply=int(token_economics.first_phase_total_supply),
        _firstPhaseMaxIssuance=int(token_economics.first_phase_max_issuance)
    )

    tx = dispatcher.functions.upgrade(issuer_library_2.address).transact()
    testerchain.wait_for_receipt(tx)
    assert contract.functions.genesisSecondsPerPeriod().call() == token_economics.seconds_per_period
    assert contract.functions.secondsPerPeriod().call() == 2 * token_economics.seconds_per_period
    assert contract.functions.getCurrentPeriod().call() == (current_period + 2) // 2
    assert contract.functions.currentMintingPeriod().call() == current_minting_period // 4
