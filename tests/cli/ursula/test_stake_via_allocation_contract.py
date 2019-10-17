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

import json

import pytest
from web3 import Web3

from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.agents import StakingEscrowAgent, ContractAgency, PreallocationEscrowAgent, NucypherTokenAgent
from nucypher.blockchain.eth.token import NU, Stake
from nucypher.cli.main import nucypher_cli
from nucypher.utilities.sandbox.constants import (
    TEST_PROVIDER_URI,
    INSECURE_DEVELOPMENT_PASSWORD,
)

#
# This test module is intended to mirror tests/cli/ursula/test_stakeholder_and_ursula.py,
# but using a staking contract (namely, PreallocationEscrow)
#


@pytest.fixture(scope='module')
def beneficiary(testerchain):
    # First, let's be give the beneficiary some cash for TXs
    beneficiary = testerchain.unassigned_accounts[0]
    tx = {'to': beneficiary,
          'from': testerchain.etherbase_account,
          'value': Web3.toWei('1', 'ether')}

    txhash = testerchain.client.w3.eth.sendTransaction(tx)
    _receipt = testerchain.wait_for_receipt(txhash)
    return beneficiary


@pytest.fixture(scope='module')
def preallocation_escrow_agent(beneficiary, test_registry, mock_allocation_registry):
    preallocation_escrow_agent = PreallocationEscrowAgent(beneficiary=beneficiary,
                                                          registry=test_registry,
                                                          allocation_registry=mock_allocation_registry)
    return preallocation_escrow_agent


def test_stake_via_contract(click_runner,
                            custom_filepath,
                            test_registry,
                            mock_allocation_registry,
                            mock_registry_filepath,
                            testerchain,
                            stakeholder_configuration_file_location,
                            stake_value,
                            token_economics,
                            agency,
                            beneficiary,
                            preallocation_escrow_agent
                            ):

    #
    # Inital setup and checks: beneficiary and pre-allocation contract
    #

    # First, let's be sure the beneficiary is in the allocation registry...
    assert mock_allocation_registry.is_beneficiary_enrolled(beneficiary)

    # ... and that the pre-allocation contract has enough tokens
    preallocation_contract_address = preallocation_escrow_agent.principal_contract.address
    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    assert token_agent.get_balance(preallocation_contract_address) >= token_economics.minimum_allowed_locked

    # Let's not forget to create a stakeholder
    init_args = ('stake', 'init-stakeholder',
                 '--poa',
                 '--config-root', custom_filepath,
                 '--provider', TEST_PROVIDER_URI,
                 '--registry-filepath', mock_registry_filepath)

    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False)
    assert result.exit_code == 0

    #
    # The good stuff: Using `nucypher stake create --escrow`
    #

    # Staking contract has no stakes yet
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    stakes = list(staking_agent.get_all_stakes(staker_address=preallocation_contract_address))
    assert not stakes

    stake_args = ('stake', 'create',
                  '--config-file', stakeholder_configuration_file_location,
                  '--escrow',
                  '--beneficiary-address', beneficiary,
                  '--allocation-filepath', mock_allocation_registry.filepath,
                  '--value', stake_value.to_tokens(),
                  '--lock-periods', token_economics.minimum_locked_periods,
                  '--force')

    # TODO: This test is writing to the default system directory and ignoring updates to the passed filepath
    user_input = '0\n' + 'Y\n' + f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + 'Y\n'
    result = click_runner.invoke(nucypher_cli, stake_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # Test integration with BaseConfiguration
    with open(stakeholder_configuration_file_location, 'r') as config_file:
        _config_data = json.loads(config_file.read())

    # Verify the stake is on-chain
    # Test integration with Agency
    stakes = list(staking_agent.get_all_stakes(staker_address=preallocation_contract_address))
    assert len(stakes) == 1

    # Test integration with NU
    start_period, end_period, value = stakes[0]
    assert NU(int(value), 'NuNit') == stake_value
    assert (end_period - start_period) == token_economics.minimum_locked_periods - 1

    # Test integration with Stake
    stake = Stake.from_stake_info(index=0,
                                  checksum_address=preallocation_contract_address,
                                  stake_info=stakes[0],
                                  staking_agent=staking_agent,
                                  economics=token_economics)
    assert stake.value == stake_value
    assert stake.duration == token_economics.minimum_locked_periods


def test_stake_set_worker(click_runner,
                          beneficiary,
                          mock_allocation_registry,
                          test_registry,
                          manual_worker,
                          stakeholder_configuration_file_location):

    init_args = ('stake', 'set-worker',
                 '--config-file', stakeholder_configuration_file_location,
                 '--escrow',
                 '--beneficiary-address', beneficiary,
                 '--allocation-filepath', mock_allocation_registry.filepath,
                 '--worker-address', manual_worker,
                 '--force')

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}'
    result = click_runner.invoke(nucypher_cli,
                                 init_args,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    staker = Staker(is_me=True,
                    checksum_address=beneficiary,
                    allocation_registry=mock_allocation_registry,
                    registry=test_registry)

    assert staker.worker_address == manual_worker


def test_stake_restake(click_runner,
                       beneficiary,
                       preallocation_escrow_agent,
                       mock_allocation_registry,
                       test_registry,
                       manual_worker,
                       testerchain,
                       stakeholder_configuration_file_location):

    staker = Staker(is_me=True,
                    checksum_address=beneficiary,
                    registry=test_registry,
                    allocation_registry=mock_allocation_registry)
    assert not staker.is_restaking

    restake_args = ('stake', 'restake',
                    '--enable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--escrow',
                    '--beneficiary-address', beneficiary,
                    '--allocation-filepath', mock_allocation_registry.filepath,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 restake_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert staker.is_restaking
    assert "Successfully enabled" in result.output

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    current_period = staking_agent.get_current_period()
    release_period = current_period + 1
    lock_args = ('stake', 'restake',
                 '--lock-until', release_period,
                 '--config-file', stakeholder_configuration_file_location,
                 '--escrow',
                 '--beneficiary-address', beneficiary,
                 '--allocation-filepath', mock_allocation_registry.filepath,
                 '--force')

    result = click_runner.invoke(nucypher_cli,
                                 lock_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # Still staking and the lock is enabled
    assert staker.is_restaking
    assert staker.restaking_lock_enabled

    # CLI Output includes success message
    assert "Successfully enabled" in result.output
    assert str(release_period) in result.output

    # Wait until release period
    testerchain.time_travel(periods=1)
    assert not staker.restaking_lock_enabled
    assert staker.is_restaking

    disable_args = ('stake', 'restake',
                    '--disable',
                    '--config-file', stakeholder_configuration_file_location,
                    '--escrow',
                    '--beneficiary-address', beneficiary,
                    '--allocation-filepath', mock_allocation_registry.filepath,
                    '--force')

    result = click_runner.invoke(nucypher_cli,
                                 disable_args,
                                 input=INSECURE_DEVELOPMENT_PASSWORD,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    allocation_contract_address = preallocation_escrow_agent.principal_contract.address
    assert not staking_agent.is_restaking(allocation_contract_address)

    staker = Staker(is_me=True,
                    checksum_address=beneficiary,
                    registry=test_registry,
                    allocation_registry=mock_allocation_registry)
    assert not staker.is_restaking
    assert "Successfully disabled" in result.output
