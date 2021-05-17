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
import datetime
import math
import re
from decimal import Decimal

import pytest
from eth_typing import BlockNumber
from web3 import Web3
from web3.datastructures import AttributeDict

from nucypher.blockchain.eth.clients import EthereumTesterClient
from nucypher.blockchain.eth.actors import StakeHolder, Staker
from nucypher.blockchain.eth.constants import MAX_UINT16, NULL_ADDRESS
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.blockchain.eth.token import NU, Stake
from nucypher.blockchain.eth.utils import estimate_block_number_for_period
from nucypher.cli.actions.select import select_client_account_for_staking
from nucypher.cli.commands.stake import (
    stake,
    StakeHolderConfigOptions,
    StakerOptions,
    TransactingStakerOptions
)
from nucypher.cli.literature import (
    NO_TOKENS_TO_WITHDRAW,
    COLLECTING_TOKEN_REWARD,
    CONFIRM_COLLECTING_WITHOUT_MINTING,
    NO_FEE_TO_WITHDRAW,
    COLLECTING_ETH_FEE,
    NO_MINTABLE_PERIODS,
    STILL_LOCKED_TOKENS,
    CONFIRM_MINTING,
    PROMPT_PROLONG_VALUE,
    CONFIRM_PROLONG,
    SUCCESSFUL_STAKE_PROLONG,
    PERIOD_ADVANCED_WARNING,
    PROMPT_STAKE_DIVIDE_VALUE,
    PROMPT_STAKE_EXTEND_VALUE,
    CONFIRM_BROADCAST_STAKE_DIVIDE,
    SUCCESSFUL_STAKE_DIVIDE,
    SUCCESSFUL_STAKE_INCREASE,
    PROMPT_STAKE_INCREASE_VALUE,
    CONFIRM_INCREASING_STAKE,
    PROMPT_STAKE_CREATE_VALUE,
    PROMPT_STAKE_CREATE_LOCK_PERIODS,
    CONFIRM_LARGE_STAKE_VALUE,
    CONFIRM_LARGE_STAKE_DURATION,
    CONFIRM_STAGED_STAKE,
    CONFIRM_BROADCAST_CREATE_STAKE,
    INSUFFICIENT_BALANCE_TO_INCREASE,
    MAXIMUM_STAKE_REACHED,
    INSUFFICIENT_BALANCE_TO_CREATE,
    ONLY_DISPLAYING_MERGEABLE_STAKES_NOTE,
    CONFIRM_MERGE,
    SUCCESSFUL_STAKES_MERGE,
    CONFIRM_STAKE_USE_UNLOCKED,
    TOKEN_REWARD_CURRENT,
    TOKEN_REWARD_NOT_FOUND,
    TOKEN_REWARD_PAST,
    TOKEN_REWARD_PAST_HEADER
)
from nucypher.cli.painting.staking import REWARDS_TABLE_COLUMNS, TOKEN_DECIMAL_PLACE
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import TransactingPower
from nucypher.types import StakerInfo, SubStakeInfo
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD, MOCK_PROVIDER_URI, YES


@pytest.fixture()
def surrogate_stakers(mock_testerchain, test_registry, mock_staking_agent):
    address_1 = mock_testerchain.etherbase_account
    address_2 = mock_testerchain.unassigned_accounts[0]

    mock_staking_agent.get_all_stakes.return_value = []

    def get_missing_commitments(checksum_address):
        if checksum_address == address_2:
            return 0
        else:
            return 1
    mock_staking_agent.get_missing_commitments.side_effect = get_missing_commitments

    return address_1, address_2


@pytest.fixture()
def surrogate_transacting_power(mock_testerchain, surrogate_stakers):
    staker = surrogate_stakers[0]
    power = TransactingPower(account=staker, signer=Web3Signer(mock_testerchain.client))
    return power


@pytest.fixture()
def surrogate_stakes(mock_staking_agent, token_economics, surrogate_stakers):
    value = 2 * token_economics.minimum_allowed_locked + 1
    current_period = 10
    duration = token_economics.minimum_locked_periods + 1
    final_period = current_period + duration
    stakes_1 = [SubStakeInfo(current_period - 1, final_period - 1, value),
                SubStakeInfo(current_period - 1, final_period, value),
                SubStakeInfo(current_period + 1, final_period, value),
                SubStakeInfo(current_period - 2, current_period, value // 2),
                SubStakeInfo(current_period - 2, current_period + 1, value // 2),
                SubStakeInfo(current_period - 2, current_period - 1, value),
                SubStakeInfo(current_period - 2, current_period - 2, value)]
    stakes_2 = [SubStakeInfo(current_period - 2, final_period + 2, value)]

    mock_staking_agent.get_current_period.return_value = current_period

    def get_all_stakes(staker_address):
        if staker_address == surrogate_stakers[0]:
            return stakes_1
        elif staker_address == surrogate_stakers[1]:
            return stakes_2
        else:
            return []
    mock_staking_agent.get_all_stakes.side_effect = get_all_stakes

    def get_substake_info(staker_address, stake_index):
        if staker_address == surrogate_stakers[0]:
            return stakes_1[stake_index]
        elif staker_address == surrogate_stakers[1]:
            return stakes_2[stake_index]
        else:
            return []
    mock_staking_agent.get_substake_info.side_effect = get_substake_info

    # only for calculating sub-stake status
    def get_staker_info(staker_address):
        if staker_address == surrogate_stakers[0]:
            return StakerInfo(value=0,
                              current_committed_period=current_period-1,
                              next_committed_period=current_period,
                              last_committed_period=0,
                              lock_restake_until_period=0,
                              completed_work=0,
                              worker_start_period=0,
                              worker=NULL_ADDRESS,
                              flags=bytes(0))
        else:
            return StakerInfo(value=0,
                              current_committed_period=0,
                              next_committed_period=0,
                              last_committed_period=0,
                              lock_restake_until_period=0,
                              completed_work=0,
                              worker_start_period=0,
                              worker=NULL_ADDRESS,
                              flags=bytes(0))
    mock_staking_agent.get_staker_info.side_effect = get_staker_info

    return stakes_1, stakes_2


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_stakeholder_configuration(test_emitter, test_registry, mock_testerchain, mock_staking_agent):

    stakeholder_config_options = StakeHolderConfigOptions(provider_uri=MOCK_PROVIDER_URI,
                                                          poa=None,
                                                          light=None,
                                                          registry_filepath=None,
                                                          network=TEMPORARY_DOMAIN,
                                                          signer_uri=None)

    mock_staking_agent.get_all_stakes.return_value = [SubStakeInfo(1, 2, 3)]
    force = False
    selected_index = 0
    selected_account = mock_testerchain.client.accounts[selected_index]
    expected_stakeholder = StakeHolder(registry=test_registry,
                                       domain=TEMPORARY_DOMAIN,
                                       initial_address=selected_account,
                                       signer=Web3Signer(mock_testerchain.client))
    expected_stakeholder.staker.refresh_stakes()

    staker_options = StakerOptions(config_options=stakeholder_config_options, staking_address=selected_account)
    transacting_staker_options = TransactingStakerOptions(staker_options=staker_options,
                                                          hw_wallet=None,
                                                          gas_price=None)
    stakeholder_from_configuration = transacting_staker_options.create_character(emitter=test_emitter, config_file=None)
    client_account, staking_address = select_client_account_for_staking(emitter=test_emitter,
                                                                        stakeholder=stakeholder_from_configuration,
                                                                        staking_address=selected_account)
    assert client_account == staking_address == selected_account
    assert stakeholder_from_configuration.staker.stakes == expected_stakeholder.staker.stakes
    assert stakeholder_from_configuration.checksum_address == client_account

    staker_options = StakerOptions(config_options=stakeholder_config_options, staking_address=None)
    transacting_staker_options = TransactingStakerOptions(staker_options=staker_options,
                                                          hw_wallet=None,
                                                          gas_price=None)
    stakeholder_from_configuration = transacting_staker_options.create_character(emitter=None, config_file=None)
    client_account, staking_address = select_client_account_for_staking(emitter=test_emitter,
                                                                        stakeholder=stakeholder_from_configuration,
                                                                        staking_address=selected_account)
    assert client_account == staking_address == selected_account
    assert stakeholder_from_configuration.staker.stakes == expected_stakeholder.staker.stakes
    assert stakeholder_from_configuration.checksum_address == client_account


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_no_token_reward(click_runner, surrogate_stakers, mock_staking_agent):
    # No tokens at all
    mock_staking_agent.calculate_staking_reward.return_value = 0

    collection_args = ('rewards',
                       'withdraw',
                       '--no-fees',
                       '--tokens',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_stakers[0])

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, collection_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 1
    assert NO_TOKENS_TO_WITHDRAW in result.output

    mock_staking_agent.calculate_staking_reward.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_staking_agent.collect_staking_reward.assert_not_called()
    mock_staking_agent.assert_no_transactions()


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_collecting_token_reward(click_runner, surrogate_stakers, mock_staking_agent, mocker, surrogate_transacting_power):
    mock_mintable_periods = mocker.spy(Staker, 'mintable_periods')

    # Collect some reward
    reward = NU(1, 'NU')
    staked = NU(100, 'NU')
    mock_staking_agent.calculate_staking_reward.return_value = reward.to_nunits()
    mock_staking_agent.non_withdrawable_stake.return_value = staked.to_nunits()

    collection_args = ('rewards',
                       'withdraw',
                       '--no-fees',
                       '--tokens',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_stakers[0])

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, collection_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert COLLECTING_TOKEN_REWARD.format(reward_amount=reward) in result.output

    mock_staking_agent.calculate_staking_reward.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_staking_agent.collect_staking_reward.assert_called_once_with(transacting_power=surrogate_transacting_power, replace=False)
    mock_staking_agent.non_withdrawable_stake.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_mintable_periods.assert_not_called()
    mock_staking_agent.assert_only_transactions([mock_staking_agent.collect_staking_reward])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_collecting_whole_reward_with_warning(click_runner, surrogate_stakers, mock_staking_agent, mocker, surrogate_transacting_power):
    mock_mintable_periods = mocker.spy(Staker, 'mintable_periods')

    # Collect last portion of NU with warning about periods to mint
    reward = NU(1, 'NU')
    mock_staking_agent.calculate_staking_reward.return_value = reward.to_nunits()
    mock_staking_agent.non_withdrawable_stake.return_value = 0
    mock_staking_agent.get_current_period.return_value = 10
    mock_staking_agent.get_current_committed_period.return_value = 8
    mock_staking_agent.get_next_committed_period.return_value = 9

    collection_args = ('rewards',
                       'withdraw',
                       '--no-fees',
                       '--tokens',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_stakers[0])

    user_input = '\n'.join((INSECURE_DEVELOPMENT_PASSWORD, YES))
    result = click_runner.invoke(stake, collection_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert COLLECTING_TOKEN_REWARD.format(reward_amount=reward) in result.output
    assert CONFIRM_COLLECTING_WITHOUT_MINTING in result.output

    mock_staking_agent.calculate_staking_reward.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_staking_agent.collect_staking_reward.assert_called_once_with(transacting_power=surrogate_transacting_power, replace=False)
    mock_staking_agent.non_withdrawable_stake.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_staking_agent.get_current_period.assert_called()
    mock_staking_agent.get_current_committed_period.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_staking_agent.get_next_committed_period.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_mintable_periods.assert_called_once()
    mock_staking_agent.assert_only_transactions([mock_staking_agent.collect_staking_reward])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_collecting_whole_reward_without_warning(click_runner, surrogate_stakers, mock_staking_agent, mocker, surrogate_transacting_power):
    mock_mintable_periods = mocker.spy(Staker, 'mintable_periods')

    # Collect last portion of NU without warning
    reward = NU(1, 'NU')
    mock_staking_agent.calculate_staking_reward.return_value = reward.to_nunits()
    mock_staking_agent.non_withdrawable_stake.return_value = 0
    mock_staking_agent.get_current_committed_period.return_value = 0
    mock_staking_agent.get_next_committed_period.return_value = 0

    collection_args = ('rewards',
                       'withdraw',
                       '--no-fees',
                       '--tokens',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_stakers[0])

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, collection_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert COLLECTING_TOKEN_REWARD.format(reward_amount=reward) in result.output
    assert CONFIRM_COLLECTING_WITHOUT_MINTING not in result.output

    mock_staking_agent.calculate_staking_reward.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_staking_agent.collect_staking_reward.assert_called_once_with(transacting_power=surrogate_transacting_power, replace=False)
    mock_staking_agent.non_withdrawable_stake.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_staking_agent.get_current_period.assert_called()
    mock_staking_agent.get_current_committed_period.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_staking_agent.get_next_committed_period.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_mintable_periods.assert_called_once()
    mock_staking_agent.assert_only_transactions([mock_staking_agent.collect_staking_reward])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_no_policy_fee(click_runner, surrogate_stakers, mock_policy_manager_agent):
    mock_policy_manager_agent.get_fee_amount.return_value = 0

    collection_args = ('rewards',
                       'withdraw',
                       '--fees',
                       '--no-tokens',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_stakers[0])

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, collection_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 1
    assert NO_FEE_TO_WITHDRAW in result.output

    mock_policy_manager_agent.get_fee_amount.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_policy_manager_agent.collect_policy_fee.assert_not_called()
    mock_policy_manager_agent.assert_no_transactions()


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_collecting_fee(click_runner, surrogate_stakers, mock_policy_manager_agent):
    fee_amount_eth = 11
    mock_policy_manager_agent.get_fee_amount.return_value = Web3.toWei(fee_amount_eth, 'ether')

    collection_args = ('rewards',
                       'withdraw',
                       '--fees',
                       '--no-tokens',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_stakers[0])

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, collection_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert COLLECTING_ETH_FEE.format(fee_amount=fee_amount_eth) in result.output

    mock_policy_manager_agent.get_fee_amount.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_policy_manager_agent.collect_policy_fee.assert_called_once()
    mock_policy_manager_agent.assert_only_transactions([mock_policy_manager_agent.collect_policy_fee])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_nothing_to_mint(click_runner, surrogate_stakers, mock_staking_agent, mocker):
    mock_mintable_periods = mocker.spy(Staker, 'mintable_periods')
    mock_staking_agent.get_current_committed_period.return_value = 0
    mock_staking_agent.get_next_committed_period.return_value = 0

    mint_command = ('mint',
                    '--provider', MOCK_PROVIDER_URI,
                    '--network', TEMPORARY_DOMAIN,
                    '--staking-address', surrogate_stakers[0])

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, mint_command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 1
    assert NO_MINTABLE_PERIODS in result.output

    mock_staking_agent.non_withdrawable_stake.assert_not_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_staking_agent.get_current_committed_period.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_staking_agent.get_next_committed_period.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_mintable_periods.assert_called_once()
    mock_staking_agent.assert_no_transactions()


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_mint_with_warning(click_runner, surrogate_stakers, mock_staking_agent, mocker):
    mock_mintable_periods = mocker.spy(Staker, 'mintable_periods')
    mock_staking_agent.get_current_period.return_value = 10
    mock_staking_agent.get_current_committed_period.return_value = 9
    mock_staking_agent.get_next_committed_period.return_value = 8
    mock_staking_agent.non_withdrawable_stake.return_value = NU(1, 'NU').to_nunits()

    mint_command = ('mint',
                    '--provider', MOCK_PROVIDER_URI,
                    '--network', TEMPORARY_DOMAIN,
                    '--staking-address', surrogate_stakers[0])

    user_input = '\n'.join((INSECURE_DEVELOPMENT_PASSWORD, YES))
    result = click_runner.invoke(stake, mint_command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert STILL_LOCKED_TOKENS in result.output
    assert CONFIRM_MINTING.format(mintable_periods=2) in result.output

    mock_staking_agent.non_withdrawable_stake.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_staking_agent.get_current_period.assert_called()
    mock_staking_agent.get_current_committed_period.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_staking_agent.get_next_committed_period.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_mintable_periods.assert_called_once()
    mock_staking_agent.assert_only_transactions([mock_staking_agent.mint])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_mint_without_warning(click_runner, surrogate_stakers, mock_staking_agent, mocker):
    mock_mintable_periods = mocker.spy(Staker, 'mintable_periods')
    mock_staking_agent.get_current_period.return_value = 10
    mock_staking_agent.get_current_committed_period.return_value = 0
    mock_staking_agent.get_next_committed_period.return_value = 8
    mock_staking_agent.non_withdrawable_stake.return_value = 0

    mint_command = ('mint',
                    '--provider', MOCK_PROVIDER_URI,
                    '--network', TEMPORARY_DOMAIN,
                    '--staking-address', surrogate_stakers[0])

    user_input = '\n'.join((INSECURE_DEVELOPMENT_PASSWORD, YES))
    result = click_runner.invoke(stake, mint_command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert STILL_LOCKED_TOKENS not in result.output
    assert CONFIRM_MINTING.format(mintable_periods=1) in result.output

    mock_staking_agent.non_withdrawable_stake.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_staking_agent.get_current_period.assert_called()
    mock_staking_agent.get_current_committed_period.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_staking_agent.get_next_committed_period.assert_called_once_with(staker_address=surrogate_stakers[0])
    mock_mintable_periods.assert_called_once()
    mock_staking_agent.assert_only_transactions([mock_staking_agent.mint])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_prolong_interactive(click_runner,
                             mocker,
                             surrogate_stakers,
                             surrogate_stakes,
                             mock_staking_agent,
                             token_economics,
                             mock_testerchain,
                             surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0
    sub_stake_index = 1
    lock_periods = 10
    final_period = surrogate_stakes[selected_index][sub_stake_index][1]

    command = ('prolong',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN)

    user_input = '\n'.join((str(selected_index),
                            str(sub_stake_index),
                            str(lock_periods),
                            YES,
                            INSECURE_DEVELOPMENT_PASSWORD))
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert PROMPT_PROLONG_VALUE.format(minimum=1, maximum=MAX_UINT16 - final_period) in result.output
    assert CONFIRM_PROLONG.format(lock_periods=lock_periods) in result.output
    assert SUCCESSFUL_STAKE_PROLONG in result.output
    assert PERIOD_ADVANCED_WARNING not in result.output

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_staking_agent.prolong_stake.assert_called_once_with(transacting_power=surrogate_transacting_power,
                                                             stake_index=sub_stake_index,
                                                             periods=lock_periods)
    mock_staking_agent.assert_only_transactions([mock_staking_agent.prolong_stake])
    mock_staking_agent.get_substake_info.assert_called_once_with(staker_address=surrogate_stakers[0],
                                                                 stake_index=sub_stake_index)


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_prolong_non_interactive(click_runner,
                                 mocker,
                                 surrogate_stakers,
                                 surrogate_stakes,
                                 mock_staking_agent,
                                 token_economics,
                                 mock_testerchain,
                                 surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0
    sub_stake_index = 1
    lock_periods = 10
    final_period = surrogate_stakes[selected_index][sub_stake_index][1]

    command = ('prolong',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--staking-address', surrogate_stakers[0],
               '--index', sub_stake_index,
               '--lock-periods', lock_periods,
               '--force')

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert PROMPT_PROLONG_VALUE.format(minimum=1, maximum=MAX_UINT16 - final_period) not in result.output
    assert CONFIRM_PROLONG.format(lock_periods=lock_periods) not in result.output
    assert SUCCESSFUL_STAKE_PROLONG in result.output
    assert PERIOD_ADVANCED_WARNING not in result.output

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_staking_agent.prolong_stake.assert_called_once_with(transacting_power=surrogate_transacting_power,
                                                             stake_index=sub_stake_index,
                                                             periods=lock_periods)
    mock_staking_agent.assert_only_transactions([mock_staking_agent.prolong_stake])
    mock_staking_agent.get_substake_info.assert_called_once_with(staker_address=surrogate_stakers[0],
                                                                 stake_index=sub_stake_index)


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_divide_interactive(click_runner,
                            mocker,
                            surrogate_stakers,
                            surrogate_stakes,
                            mock_staking_agent,
                            token_economics,
                            mock_testerchain,
                            surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0
    sub_stake_index = 1
    lock_periods = 10
    min_allowed_locked = token_economics.minimum_allowed_locked
    target_value = min_allowed_locked + 1  # Let's add some spare change to force dealing with decimal NU

    mock_staking_agent.get_worker_from_staker.return_value = NULL_ADDRESS

    command = ('divide',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN)

    user_input = '\n'.join((str(selected_index),
                            str(sub_stake_index),
                            str(NU.from_nunits(target_value).to_tokens()),
                            str(lock_periods),
                            YES,
                            INSECURE_DEVELOPMENT_PASSWORD))
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert PROMPT_STAKE_DIVIDE_VALUE.format(minimum=NU.from_nunits(min_allowed_locked),
                                            maximum=NU.from_nunits(min_allowed_locked + 1)) in result.output
    assert PROMPT_STAKE_EXTEND_VALUE in result.output
    assert CONFIRM_BROADCAST_STAKE_DIVIDE in result.output
    assert SUCCESSFUL_STAKE_DIVIDE in result.output

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_staking_agent.divide_stake.assert_called_once_with(transacting_power=surrogate_transacting_power,
                                                            stake_index=sub_stake_index,
                                                            target_value=target_value,
                                                            periods=lock_periods)
    mock_staking_agent.assert_only_transactions([mock_staking_agent.divide_stake])
    mock_staking_agent.get_substake_info.assert_called_once_with(staker_address=surrogate_stakers[0],
                                                                 stake_index=sub_stake_index)


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_divide_non_interactive(click_runner,
                                mocker,
                                surrogate_stakers,
                                surrogate_stakes,
                                mock_staking_agent,
                                token_economics,
                                mock_testerchain,
                                surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    sub_stake_index = 1
    lock_periods = 10
    min_allowed_locked = token_economics.minimum_allowed_locked
    target_value = min_allowed_locked + 1  # Let's add some spare change to force dealing with decimal NU

    mock_staking_agent.get_worker_from_staker.return_value = surrogate_stakers[0]

    command = ('divide',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--staking-address', surrogate_stakers[0],
               '--index', sub_stake_index,
               '--lock-periods', lock_periods,
               '--value', NU.from_nunits(target_value).to_tokens(),
               '--force')

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert PROMPT_STAKE_DIVIDE_VALUE.format(minimum=NU.from_nunits(min_allowed_locked),
                                            maximum=NU.from_nunits(min_allowed_locked + 1)) not in result.output
    assert PROMPT_STAKE_EXTEND_VALUE not in result.output
    assert CONFIRM_BROADCAST_STAKE_DIVIDE not in result.output
    assert SUCCESSFUL_STAKE_DIVIDE in result.output

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_staking_agent.divide_stake.assert_called_once_with(transacting_power=surrogate_transacting_power,
                                                            stake_index=sub_stake_index,
                                                            target_value=target_value,
                                                            periods=lock_periods)
    mock_staking_agent.assert_only_transactions([mock_staking_agent.divide_stake])
    mock_staking_agent.get_substake_info.assert_called_once_with(staker_address=surrogate_stakers[0],
                                                                 stake_index=sub_stake_index)


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_increase_interactive(click_runner,
                              mocker,
                              surrogate_stakers,
                              surrogate_stakes,
                              mock_token_agent,
                              mock_staking_agent,
                              token_economics,
                              mock_testerchain,
                              surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0
    sub_stake_index = 1
    additional_value = NU.from_nunits(token_economics.minimum_allowed_locked // 10 + 12345)

    mock_token_agent.get_balance.return_value = 0

    command = ('increase',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN)

    user_input = '\n'.join((str(selected_index),
                            str(sub_stake_index),
                            str(additional_value.to_tokens()),
                            YES,
                            INSECURE_DEVELOPMENT_PASSWORD))

    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 1
    assert INSUFFICIENT_BALANCE_TO_INCREASE in result.output
    assert MAXIMUM_STAKE_REACHED not in result.output
    assert SUCCESSFUL_STAKE_INCREASE not in result.output

    mock_staking_agent.get_locked_tokens.return_value = token_economics.maximum_allowed_locked
    balance = token_economics.minimum_allowed_locked * 5
    mock_token_agent.get_balance.return_value = balance

    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 1
    assert INSUFFICIENT_BALANCE_TO_INCREASE not in result.output
    assert MAXIMUM_STAKE_REACHED in result.output
    assert SUCCESSFUL_STAKE_INCREASE not in result.output

    mock_staking_agent.get_locked_tokens.return_value = token_economics.maximum_allowed_locked // 2
    current_allowance = 1
    mock_token_agent.get_allowance.return_value = current_allowance

    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    upper_limit = NU.from_nunits(balance)
    assert CONFIRM_STAKE_USE_UNLOCKED not in result.output  # default is use staker address
    assert PROMPT_STAKE_INCREASE_VALUE.format(upper_limit=upper_limit) in result.output
    assert CONFIRM_INCREASING_STAKE.format(stake_index=sub_stake_index, value=additional_value) in result.output
    assert SUCCESSFUL_STAKE_INCREASE in result.output

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_staking_agent.deposit_and_increase.assert_called_once_with(transacting_power=surrogate_transacting_power,
                                                                    stake_index=sub_stake_index,
                                                                    amount=additional_value.to_nunits())
    mock_staking_agent.assert_only_transactions([mock_staking_agent.deposit_and_increase])
    mock_staking_agent.get_substake_info.assert_called_once_with(staker_address=surrogate_stakers[0],
                                                                 stake_index=sub_stake_index)
    mock_token_agent.get_allowance.assert_called_once_with(owner=surrogate_stakers[0],
                                                           spender=mock_staking_agent.contract.address)
    mock_token_agent.increase_allowance.assert_called_once_with(transacting_power=surrogate_transacting_power,
                                                                spender_address=mock_staking_agent.contract.address,
                                                                increase=additional_value.to_nunits() - current_allowance)
    mock_token_agent.assert_only_transactions([mock_token_agent.increase_allowance])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_increase_non_interactive(click_runner,
                                  mocker,
                                  surrogate_stakers,
                                  surrogate_stakes,
                                  mock_token_agent,
                                  mock_staking_agent,
                                  token_economics,
                                  mock_testerchain,
                                  surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    sub_stake_index = 1
    additional_value = NU.from_nunits(token_economics.minimum_allowed_locked // 10 + 12345)

    locked_tokens = token_economics.minimum_allowed_locked * 5
    mock_staking_agent.get_locked_tokens.return_value = locked_tokens
    mock_token_agent.get_balance.return_value = 2 * token_economics.maximum_allowed_locked
    current_allowance = 1
    mock_token_agent.get_allowance.return_value = current_allowance

    command = ('increase',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--staking-address', surrogate_stakers[0],
               '--index', sub_stake_index,
               '--value', additional_value.to_tokens(),
               '--force')

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    upper_limit = NU.from_nunits(token_economics.maximum_allowed_locked - locked_tokens)
    assert PROMPT_STAKE_INCREASE_VALUE.format(upper_limit=upper_limit) not in result.output
    assert CONFIRM_INCREASING_STAKE.format(stake_index=sub_stake_index, value=additional_value) not in result.output
    assert SUCCESSFUL_STAKE_INCREASE in result.output
    assert CONFIRM_STAKE_USE_UNLOCKED not in result.output  # default is use staker address

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_staking_agent.deposit_and_increase.assert_called_once_with(transacting_power=surrogate_transacting_power,
                                                                    stake_index=sub_stake_index,
                                                                    amount=additional_value.to_nunits())
    mock_staking_agent.assert_only_transactions([mock_staking_agent.deposit_and_increase])
    mock_staking_agent.get_substake_info.assert_called_once_with(staker_address=surrogate_stakers[0],
                                                                 stake_index=sub_stake_index)
    mock_token_agent.get_allowance.assert_called_once_with(owner=surrogate_stakers[0],
                                                           spender=mock_staking_agent.contract.address)
    mock_token_agent.increase_allowance.assert_called_once_with(transacting_power=surrogate_transacting_power,
                                                                spender_address=mock_staking_agent.contract.address,
                                                                increase=additional_value.to_nunits() - current_allowance)
    mock_token_agent.assert_only_transactions([mock_token_agent.increase_allowance])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_increase_lock_interactive(click_runner,
                                   mocker,
                                   surrogate_stakers,
                                   surrogate_stakes,
                                   mock_staking_agent,
                                   token_economics,
                                   mock_testerchain,
                                   surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0
    sub_stake_index = len(surrogate_stakes) - 1
    additional_value = NU.from_nunits(token_economics.minimum_allowed_locked // 10 + 12345)

    mock_staking_agent.calculate_staking_reward.return_value = 0

    command = ('increase',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--from-unlocked')

    user_input = '\n'.join((str(selected_index),
                            str(sub_stake_index),
                            YES,
                            str(additional_value.to_tokens()),
                            YES,
                            INSECURE_DEVELOPMENT_PASSWORD))

    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 1
    assert INSUFFICIENT_BALANCE_TO_INCREASE in result.output
    assert MAXIMUM_STAKE_REACHED not in result.output
    assert SUCCESSFUL_STAKE_INCREASE not in result.output

    mock_staking_agent.get_locked_tokens.return_value = token_economics.maximum_allowed_locked
    unlocked_tokens = token_economics.maximum_allowed_locked
    mock_staking_agent.calculate_staking_reward.return_value = unlocked_tokens

    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 1
    assert INSUFFICIENT_BALANCE_TO_INCREASE not in result.output
    assert MAXIMUM_STAKE_REACHED in result.output
    assert SUCCESSFUL_STAKE_INCREASE not in result.output

    locked_tokens = token_economics.maximum_allowed_locked // 3
    mock_staking_agent.get_locked_tokens.return_value = locked_tokens

    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    upper_limit = NU.from_nunits(token_economics.maximum_allowed_locked - locked_tokens)
    assert PROMPT_STAKE_INCREASE_VALUE.format(upper_limit=upper_limit) in result.output
    assert CONFIRM_INCREASING_STAKE.format(stake_index=sub_stake_index, value=additional_value) in result.output
    assert SUCCESSFUL_STAKE_INCREASE in result.output
    assert CONFIRM_STAKE_USE_UNLOCKED in result.output  # value not provided but --from-unlocked specified so prompted

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_staking_agent.lock_and_increase.assert_called_once_with(transacting_power=surrogate_transacting_power,
                                                                 stake_index=sub_stake_index,
                                                                 amount=additional_value.to_nunits())
    mock_staking_agent.assert_only_transactions([mock_staking_agent.lock_and_increase])
    mock_staking_agent.get_substake_info.assert_called_once_with(staker_address=surrogate_stakers[selected_index],
                                                                 stake_index=sub_stake_index)


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_increase_lock_non_interactive(click_runner,
                                       mocker,
                                       surrogate_stakers,
                                       surrogate_stakes,
                                       mock_staking_agent,
                                       token_economics,
                                       mock_testerchain,
                                       surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0
    sub_stake_index = len(surrogate_stakes) - 1
    additional_value = NU.from_nunits(token_economics.minimum_allowed_locked // 10 + 12345)

    mock_staking_agent.get_locked_tokens.return_value = token_economics.minimum_allowed_locked * 2
    unlocked_tokens = token_economics.minimum_allowed_locked * 5
    mock_staking_agent.calculate_staking_reward.return_value = unlocked_tokens

    command = ('increase',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--staking-address', surrogate_stakers[selected_index],
               '--index', sub_stake_index,
               '--value', additional_value.to_tokens(),
               '--from-unlocked',
               '--force')

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    upper_limit = NU.from_nunits(unlocked_tokens)
    assert CONFIRM_STAKE_USE_UNLOCKED not in result.output  # value provided so not prompted
    assert PROMPT_STAKE_INCREASE_VALUE.format(upper_limit=upper_limit) not in result.output
    assert CONFIRM_INCREASING_STAKE.format(stake_index=sub_stake_index, value=additional_value) not in result.output
    assert SUCCESSFUL_STAKE_INCREASE in result.output

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_staking_agent.lock_and_increase.assert_called_once_with(transacting_power=surrogate_transacting_power,
                                                                 stake_index=sub_stake_index,
                                                                 amount=additional_value.to_nunits())
    mock_staking_agent.assert_only_transactions([mock_staking_agent.lock_and_increase])
    mock_staking_agent.get_substake_info.assert_called_once_with(staker_address=surrogate_stakers[selected_index],
                                                                 stake_index=sub_stake_index)


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_create_interactive(click_runner,
                            mocker,
                            surrogate_stakers,
                            surrogate_stakes,
                            mock_token_agent,
                            mock_staking_agent,
                            token_economics,
                            mock_testerchain,
                            surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0
    lock_periods = 366
    value = NU.from_nunits(token_economics.minimum_allowed_locked * 11 + 12345)

    command = ('create',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN)

    user_input = '\n'.join((str(selected_index),
                            YES,
                            str(value.to_tokens()),
                            str(lock_periods),
                            YES,
                            YES,
                            YES,
                            YES,
                            INSECURE_DEVELOPMENT_PASSWORD))

    # insufficient existing balance
    mock_token_agent.get_balance.return_value = token_economics.minimum_allowed_locked - 1
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 1
    assert INSUFFICIENT_BALANCE_TO_CREATE in result.output
    assert MAXIMUM_STAKE_REACHED not in result.output
    assert SUCCESSFUL_STAKE_INCREASE not in result.output

    # already at max stake
    mock_staking_agent.get_locked_tokens.return_value = token_economics.maximum_allowed_locked
    balance = token_economics.minimum_allowed_locked * 12
    mock_token_agent.get_balance.return_value = balance

    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 1
    assert INSUFFICIENT_BALANCE_TO_CREATE not in result.output
    assert MAXIMUM_STAKE_REACHED in result.output
    assert SUCCESSFUL_STAKE_INCREASE not in result.output

    # successfully stake minimum allowed which equals available balance
    mock_staking_agent.get_locked_tokens.return_value = token_economics.minimum_allowed_locked
    mock_token_agent.get_balance.return_value = token_economics.minimum_allowed_locked
    min_stake_value = NU.from_nunits(token_economics.minimum_allowed_locked)
    min_amount_user_input = '\n'.join((str(selected_index),
                                       YES,
                                       str(min_stake_value.to_tokens()),
                                       str(lock_periods),
                                       YES,
                                       YES,
                                       YES,
                                       INSECURE_DEVELOPMENT_PASSWORD))
    result = click_runner.invoke(stake, command, input=min_amount_user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert CONFIRM_STAKE_USE_UNLOCKED not in result.output  # default is to use staker address
    assert INSUFFICIENT_BALANCE_TO_CREATE not in result.output
    assert PROMPT_STAKE_CREATE_VALUE.format(lower_limit=min_stake_value, upper_limit=min_stake_value) in result.output
    assert CONFIRM_STAGED_STAKE.format(nunits=str(min_stake_value.to_nunits()),
                                       tokens=min_stake_value,
                                       staker_address=surrogate_stakers[selected_index],
                                       lock_periods=lock_periods) in result.output
    assert CONFIRM_BROADCAST_CREATE_STAKE in result.output

    # successfully stake large stake
    mock_staking_agent.get_locked_tokens.return_value = token_economics.maximum_allowed_locked // 2
    mock_token_agent.get_balance.return_value = balance
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    upper_limit = NU.from_nunits(balance)
    lower_limit = NU.from_nunits(token_economics.minimum_allowed_locked)
    min_locktime = token_economics.minimum_locked_periods
    max_locktime = MAX_UINT16 - 10  # MAX_UINT16 - current period

    assert CONFIRM_STAKE_USE_UNLOCKED not in result.output  # default is to use staker address
    assert PROMPT_STAKE_CREATE_VALUE.format(lower_limit=lower_limit, upper_limit=upper_limit) in result.output
    assert PROMPT_STAKE_CREATE_LOCK_PERIODS.format(min_locktime=min_locktime, max_locktime=max_locktime) in result.output
    assert CONFIRM_STAGED_STAKE.format(nunits=str(value.to_nunits()),
                                       tokens=value,
                                       staker_address=surrogate_stakers[selected_index],
                                       lock_periods=lock_periods) in result.output
    assert CONFIRM_BROADCAST_CREATE_STAKE in result.output
    assert CONFIRM_LARGE_STAKE_VALUE.format(value=value) in result.output
    lock_days = (lock_periods * token_economics.hours_per_period) // 24
    assert CONFIRM_LARGE_STAKE_DURATION.format(lock_periods=lock_periods, lock_days=lock_days) in result.output

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_token_agent.approve_and_call.assert_called_with(amount=value.to_nunits(),
                                                         target_address=mock_staking_agent.contract_address,
                                                         transacting_power=surrogate_transacting_power,
                                                         call_data=Web3.toBytes(lock_periods))
    mock_token_agent.assert_only_transactions([mock_token_agent.decrease_allowance, mock_token_agent.approve_and_call])
    mock_staking_agent.assert_no_transactions()


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_create_non_interactive(click_runner,
                                mocker,
                                surrogate_stakers,
                                surrogate_stakes,
                                mock_token_agent,
                                mock_staking_agent,
                                token_economics,
                                mock_testerchain,
                                surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0

    lock_periods = token_economics.minimum_locked_periods
    value = NU.from_nunits(token_economics.minimum_allowed_locked * 2 + 12345)

    locked_tokens = token_economics.minimum_allowed_locked * 5
    mock_staking_agent.get_locked_tokens.return_value = locked_tokens
    mock_token_agent.get_balance.return_value = token_economics.maximum_allowed_locked

    command = ('create',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--staking-address', surrogate_stakers[selected_index],
               '--lock-periods', lock_periods,
               '--value', value.to_tokens(),
               '--force')

    user_input = '\n'.join((YES, INSECURE_DEVELOPMENT_PASSWORD))
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    upper_limit = NU.from_nunits(token_economics.maximum_allowed_locked - locked_tokens)
    lower_limit = NU.from_nunits(token_economics.minimum_allowed_locked)
    min_locktime = token_economics.minimum_locked_periods
    max_locktime = MAX_UINT16 - 10  # MAX_UINT16 - current period

    assert CONFIRM_STAKE_USE_UNLOCKED not in result.output  # default is to use staker address
    assert PROMPT_STAKE_CREATE_VALUE.format(lower_limit=lower_limit, upper_limit=upper_limit) not in result.output
    assert PROMPT_STAKE_CREATE_LOCK_PERIODS.format(min_locktime=min_locktime, max_locktime=max_locktime) not in result.output
    assert CONFIRM_STAGED_STAKE.format(nunits=str(value.to_nunits()),
                                       tokens=value,
                                       staker_address=surrogate_stakers[selected_index],
                                       lock_periods=lock_periods) not in result.output
    assert CONFIRM_BROADCAST_CREATE_STAKE in result.output
    assert CONFIRM_LARGE_STAKE_VALUE.format(value=value) not in result.output
    lock_days = (lock_periods * token_economics.hours_per_period) // 24
    assert CONFIRM_LARGE_STAKE_DURATION.format(lock_periods=lock_periods, lock_days=lock_days) not in result.output

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_token_agent.get_allowance.assert_called()
    mock_token_agent.approve_and_call.assert_called_once_with(amount=value.to_nunits(),
                                                              target_address=mock_staking_agent.contract_address,
                                                              transacting_power=surrogate_transacting_power,
                                                              call_data=Web3.toBytes(lock_periods))
    mock_token_agent.assert_only_transactions([mock_token_agent.decrease_allowance, mock_token_agent.approve_and_call])
    mock_staking_agent.assert_no_transactions()


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_create_lock_interactive(click_runner,
                                 mocker,
                                 surrogate_stakers,
                                 surrogate_stakes,
                                 mock_staking_agent,
                                 token_economics,
                                 mock_testerchain,
                                 surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0
    lock_periods = 366
    value = NU.from_nunits(token_economics.minimum_allowed_locked * 2 + 12345)

    mock_staking_agent.calculate_staking_reward.return_value = token_economics.minimum_allowed_locked - 1

    command = ('create',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--from-unlocked')

    user_input = '\n'.join((str(selected_index),
                            YES,
                            str(value.to_tokens()),
                            str(lock_periods),
                            YES,
                            YES,
                            YES,
                            INSECURE_DEVELOPMENT_PASSWORD))

    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 1
    assert INSUFFICIENT_BALANCE_TO_CREATE in result.output
    assert MAXIMUM_STAKE_REACHED not in result.output
    assert SUCCESSFUL_STAKE_INCREASE not in result.output

    mock_staking_agent.get_locked_tokens.return_value = token_economics.maximum_allowed_locked
    mock_staking_agent.calculate_staking_reward.return_value = token_economics.maximum_allowed_locked

    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 1
    assert INSUFFICIENT_BALANCE_TO_CREATE not in result.output
    assert MAXIMUM_STAKE_REACHED in result.output
    assert SUCCESSFUL_STAKE_INCREASE not in result.output

    locked_tokens = token_economics.maximum_allowed_locked // 3
    mock_staking_agent.get_locked_tokens.return_value = locked_tokens

    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    upper_limit = NU.from_nunits(token_economics.maximum_allowed_locked - locked_tokens)
    lower_limit = NU.from_nunits(token_economics.minimum_allowed_locked)
    min_locktime = token_economics.minimum_locked_periods
    max_locktime = MAX_UINT16 - 10  # MAX_UINT16 - current period

    assert CONFIRM_STAKE_USE_UNLOCKED in result.output  # value not provided but --from-unlocked specified so prompted
    assert PROMPT_STAKE_CREATE_VALUE.format(lower_limit=lower_limit, upper_limit=upper_limit) in result.output
    assert PROMPT_STAKE_CREATE_LOCK_PERIODS.format(min_locktime=min_locktime, max_locktime=max_locktime) in result.output
    assert CONFIRM_STAGED_STAKE.format(nunits=str(value.to_nunits()),
                                       tokens=value,
                                       staker_address=surrogate_stakers[selected_index],
                                       lock_periods=lock_periods) in result.output
    assert CONFIRM_BROADCAST_CREATE_STAKE in result.output
    assert CONFIRM_LARGE_STAKE_VALUE.format(value=value) not in result.output
    lock_days = (lock_periods * token_economics.hours_per_period) // 24
    assert CONFIRM_LARGE_STAKE_DURATION.format(lock_periods=lock_periods, lock_days=lock_days) in result.output

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_staking_agent.lock_and_create.assert_called_once_with(amount=value.to_nunits(),
                                                               lock_periods=lock_periods,
                                                               transacting_power=surrogate_transacting_power)
    mock_staking_agent.assert_only_transactions([mock_staking_agent.lock_and_create])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_create_lock_non_interactive(click_runner,
                                     mocker,
                                     surrogate_stakers,
                                     surrogate_stakes,
                                     mock_staking_agent,
                                     token_economics,
                                     mock_testerchain,
                                     surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0

    lock_periods = token_economics.minimum_locked_periods
    value = NU.from_nunits(token_economics.minimum_allowed_locked * 11 + 12345)

    mock_staking_agent.get_locked_tokens.return_value = token_economics.minimum_allowed_locked * 5
    unlocked_tokens = token_economics.maximum_allowed_locked // 2
    mock_staking_agent.calculate_staking_reward.return_value = unlocked_tokens

    command = ('create',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--staking-address', surrogate_stakers[selected_index],
               '--lock-periods', lock_periods,
               '--value', value.to_tokens(),
               '--from-unlocked',
               '--force')

    user_input = '\n'.join((YES, YES, INSECURE_DEVELOPMENT_PASSWORD))
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    upper_limit = NU.from_nunits(unlocked_tokens)
    lower_limit = NU.from_nunits(token_economics.minimum_allowed_locked)
    min_locktime = token_economics.minimum_locked_periods
    max_locktime = MAX_UINT16 - 10  # MAX_UINT16 - current period

    assert CONFIRM_STAKE_USE_UNLOCKED not in result.output  # value provided so not prompted
    assert PROMPT_STAKE_CREATE_VALUE.format(lower_limit=lower_limit, upper_limit=upper_limit) not in result.output
    assert PROMPT_STAKE_CREATE_LOCK_PERIODS.format(min_locktime=min_locktime, max_locktime=max_locktime) not in result.output
    assert CONFIRM_STAGED_STAKE.format(nunits=str(value.to_nunits()),
                                       tokens=value,
                                       staker_address=surrogate_stakers[selected_index],
                                       lock_periods=lock_periods) not in result.output
    assert CONFIRM_BROADCAST_CREATE_STAKE in result.output
    assert CONFIRM_LARGE_STAKE_VALUE.format(value=value) not in result.output
    lock_days = (lock_periods * token_economics.hours_per_period) // 24
    assert CONFIRM_LARGE_STAKE_DURATION.format(lock_periods=lock_periods, lock_days=lock_days) not in result.output

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_staking_agent.lock_and_create.assert_called_once_with(amount=value.to_nunits(),
                                                               lock_periods=lock_periods,
                                                               transacting_power=surrogate_transacting_power)
    mock_staking_agent.assert_only_transactions([mock_staking_agent.lock_and_create])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_merge_interactive(click_runner,
                           mocker,
                           surrogate_stakers,
                           surrogate_stakes,
                           mock_staking_agent,
                           token_economics,
                           mock_testerchain,
                           surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0
    sub_stake_index_1 = 1
    sub_stake_index_2 = 2

    command = ('merge',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN)

    user_input = '\n'.join((str(selected_index),
                            str(sub_stake_index_1),
                            str(sub_stake_index_2),
                            YES,
                            INSECURE_DEVELOPMENT_PASSWORD))

    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    final_period = surrogate_stakes[selected_index][sub_stake_index_1].last_period
    assert ONLY_DISPLAYING_MERGEABLE_STAKES_NOTE.format(final_period=final_period) in result.output
    assert CONFIRM_MERGE.format(stake_index_1=sub_stake_index_1, stake_index_2=sub_stake_index_2) in result.output
    assert SUCCESSFUL_STAKES_MERGE in result.output

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_staking_agent.merge_stakes.assert_called_once_with(transacting_power=surrogate_transacting_power,
                                                            stake_index_1=sub_stake_index_1,
                                                            stake_index_2=sub_stake_index_2)
    mock_staking_agent.assert_only_transactions([mock_staking_agent.merge_stakes])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_merge_partially_interactive(click_runner,
                                     mocker,
                                     surrogate_stakers,
                                     surrogate_stakes,
                                     mock_staking_agent,
                                     token_economics,
                                     mock_testerchain,
                                     surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0
    sub_stake_index_1 = 1
    sub_stake_index_2 = 2

    base_command = ('merge',
                    '--provider', MOCK_PROVIDER_URI,
                    '--network', TEMPORARY_DOMAIN,
                    '--staking-address', surrogate_stakers[selected_index])
    user_input = '\n'.join((str(sub_stake_index_2),
                            YES,
                            INSECURE_DEVELOPMENT_PASSWORD))

    command = base_command + ('--index-1', sub_stake_index_1)
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    final_period = surrogate_stakes[selected_index][sub_stake_index_1].last_period
    assert ONLY_DISPLAYING_MERGEABLE_STAKES_NOTE.format(final_period=final_period) in result.output
    assert CONFIRM_MERGE.format(stake_index_1=sub_stake_index_1, stake_index_2=sub_stake_index_2) in result.output
    assert SUCCESSFUL_STAKES_MERGE in result.output

    command = base_command + ('--index-2', sub_stake_index_1)
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    final_period = surrogate_stakes[selected_index][sub_stake_index_1].last_period
    assert ONLY_DISPLAYING_MERGEABLE_STAKES_NOTE.format(final_period=final_period) in result.output
    assert CONFIRM_MERGE.format(stake_index_1=sub_stake_index_1, stake_index_2=sub_stake_index_2) in result.output
    assert SUCCESSFUL_STAKES_MERGE in result.output

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_staking_agent.merge_stakes.assert_called_with(transacting_power=surrogate_transacting_power,
                                                       stake_index_1=sub_stake_index_1,
                                                       stake_index_2=sub_stake_index_2)
    mock_staking_agent.assert_only_transactions([mock_staking_agent.merge_stakes])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_merge_non_interactive(click_runner,
                               mocker,
                               surrogate_stakers,
                               surrogate_stakes,
                               mock_staking_agent,
                               token_economics,
                               mock_testerchain,
                               surrogate_transacting_power):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0
    sub_stake_index_1 = 1
    sub_stake_index_2 = 2

    mock_staking_agent.get_locked_tokens.return_value = token_economics.minimum_allowed_locked * 2
    unlocked_tokens = token_economics.minimum_allowed_locked * 5
    mock_staking_agent.calculate_staking_reward.return_value = unlocked_tokens

    command = ('merge',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--staking-address', surrogate_stakers[selected_index],
               '--index-1', sub_stake_index_1,
               '--index-2', sub_stake_index_2,
               '--force')

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    final_period = surrogate_stakes[selected_index][sub_stake_index_1].last_period
    assert ONLY_DISPLAYING_MERGEABLE_STAKES_NOTE.format(final_period=final_period) not in result.output
    assert CONFIRM_MERGE.format(stake_index_1=sub_stake_index_1, stake_index_2=sub_stake_index_2) not in result.output
    assert SUCCESSFUL_STAKES_MERGE in result.output

    mock_staking_agent.get_all_stakes.assert_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_refresh_stakes.assert_called()
    mock_staking_agent.merge_stakes.assert_called_once_with(transacting_power=surrogate_transacting_power,
                                                            stake_index_1=sub_stake_index_1,
                                                            stake_index_2=sub_stake_index_2)
    mock_staking_agent.assert_only_transactions([mock_staking_agent.merge_stakes])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_stake_list_active(click_runner,
                           surrogate_stakers,
                           surrogate_stakes,
                           token_economics,
                           mocker,
                           get_random_checksum_address):

    command = ('list',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,)

    user_input = None
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    assert re.search("Status\\s+Missing 1 commitments", result.output, re.MULTILINE)
    assert re.search("Status\\s+Committed #1", result.output, re.MULTILINE)

    statuses = [Stake.Status.DIVISIBLE,
                Stake.Status.DIVISIBLE,
                Stake.Status.DIVISIBLE,
                Stake.Status.LOCKED,
                Stake.Status.EDITABLE,
                Stake.Status.UNLOCKED,
                Stake.Status.INACTIVE]

    current_period = 10
    mock_staking_agent = mocker.Mock()
    mock_staking_agent.get_current_period = mocker.Mock(return_value=current_period)

    for stakes in surrogate_stakes:
        for index, sub_stake_info in enumerate(stakes):

            value = NU.from_nunits(sub_stake_info.locked_value)

            sub_stake = Stake(staking_agent=mock_staking_agent,
                              checksum_address=get_random_checksum_address(),
                              value=value,
                              first_locked_period=sub_stake_info.first_period,
                              final_locked_period=sub_stake_info.last_period,
                              index=index,
                              economics=token_economics)

            sub_stake.status = mocker.Mock(return_value=statuses[index])

            sub_stake_data = sub_stake.describe()

            search = f"{sub_stake_data['index']}\\s+│\\s+" \
                     f"{sub_stake_data['value']}\\s+│\\s+" \
                     f"{sub_stake_data['remaining']}\\s+│\\s+" \
                     f"{sub_stake_data['enactment']}\\s+│\\s+" \
                     f"{sub_stake_data['last_period']}\\s+│\\s+" \
                     f"{sub_stake_data['boost']}\\s+│\\s+" \
                     f"{sub_stake_data['status']}"

            # locked sub-stakes
            if index < 5:
                assert re.search(search, result.output, re.MULTILINE)
            # unlocked sub-stakes
            else:
                assert not re.search(search, result.output, re.MULTILINE)


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_stake_list_all(click_runner,
                        surrogate_stakers,
                        surrogate_stakes,
                        token_economics,
                        surrogate_transacting_power,
                        mocker,
                        get_random_checksum_address):

    command = ('list',
               '--all',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,)

    user_input = None
    result = click_runner.invoke(stake, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    assert re.search("Status\\s+Missing 1 commitments", result.output, re.MULTILINE)
    assert re.search("Status\\s+Committed #1", result.output, re.MULTILINE)

    statuses = [Stake.Status.DIVISIBLE,
                Stake.Status.DIVISIBLE,
                Stake.Status.DIVISIBLE,
                Stake.Status.LOCKED,
                Stake.Status.EDITABLE,
                Stake.Status.UNLOCKED,
                Stake.Status.INACTIVE]

    current_period = 10
    mock_staking_agent = mocker.Mock()
    mock_staking_agent.get_current_period = mocker.Mock(return_value=current_period)

    for stakes in surrogate_stakes:
        for index, sub_stake_info in enumerate(stakes):
            value = NU.from_nunits(sub_stake_info.locked_value)

            sub_stake = Stake(staking_agent=mock_staking_agent,
                              checksum_address=get_random_checksum_address(),
                              value=value,
                              first_locked_period=sub_stake_info.first_period,
                              final_locked_period=sub_stake_info.last_period,
                              index=index,
                              economics=token_economics)

            status = statuses[index]
            sub_stake.status = mocker.Mock(return_value=status)
            sub_stake_data = sub_stake.describe()

            if status == Stake.Status.INACTIVE:
                sub_stake_data['remaining'] = 'N/A'
                sub_stake_data['last_period'] = 'N/A'
                sub_stake_data['boost'] = 'N/A'

            search = f"{sub_stake_data['index']}\\s+│\\s+" \
                     f"{sub_stake_data['value']}\\s+│\\s+" \
                     f"{sub_stake_data['remaining']}\\s+│\\s+" \
                     f"{sub_stake_data['enactment']}\\s+│\\s+" \
                     f"{sub_stake_data['last_period']}\\s+│\\s+" \
                     f"{sub_stake_data['boost']}\\s+│\\s+" \
                     f"{sub_stake_data['status']}"

            assert re.search(search, result.output, re.MULTILINE)


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_show_rewards(click_runner, surrogate_stakers, mock_staking_agent):
    reward_amount = 1
    reward = NU(reward_amount, 'NU')
    mock_staking_agent.calculate_staking_reward.return_value = reward.to_nunits()

    command = ('rewards',
               'show',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--staking-address', surrogate_stakers[0])

    result = click_runner.invoke(stake, command, catch_exceptions=False)
    assert result.exit_code == 0
    assert TOKEN_REWARD_CURRENT.format(reward_amount=round(reward, TOKEN_DECIMAL_PLACE)) in result.output

    mock_staking_agent.calculate_staking_reward.assert_called_once_with(staker_address=surrogate_stakers[0])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_show_rewards_for_period(click_runner, surrogate_stakers, mock_staking_agent, token_economics, mocker):
    periods = 30
    periods_per_day = token_economics.hours_per_period // 24
    seconds_per_period = token_economics.seconds_per_period
    latest_block = 100_000_000
    latest_period = 15_000

    reward_amount = 1
    nr_of_events = 3
    events = [{
        'args': {
            'value': NU(Decimal(reward_amount + i/100*i), 'NU').to_nunits(),
            'period': latest_period - i,
        },
        'blockNumber': estimate_block_number_for_period(latest_period - i,
                                                        seconds_per_period,
                                                        BlockNumber(latest_block - i * 100)),
    } for i in range(nr_of_events)]

    event_name = 'Minted'
    event = mocker.Mock()
    event.getLogs = mocker.MagicMock(return_value=events)

    mock_staking_agent.contract.events = {event_name: event}
    mocker.patch.object(EthereumTesterClient,
                        'block_number',
                        return_value=latest_block,
                        new_callable=mocker.PropertyMock)
    mocker.patch.object(EthereumTesterClient,
                        'get_block',
                        return_value=AttributeDict({'timestamp': datetime.datetime.timestamp(datetime.datetime.now())}),
                        new_callable=mocker.MagicMock)

    command = ('rewards',
               'show',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--staking-address', surrogate_stakers[0],
               '--periods', periods)
    result = click_runner.invoke(stake, command, catch_exceptions=False)

    assert result.exit_code == 0
    periods_as_days = math.floor(periods_per_day * periods)

    assert TOKEN_REWARD_PAST_HEADER.format(periods=periods, days=periods_as_days) in result.output
    for header in REWARDS_TABLE_COLUMNS:
        assert header in result.output
    for event in events:
        assert str(event['blockNumber']) in result.output

    rewards_total = sum([e['args']['value'] for e in events])
    rewards_total = NU(rewards_total, 'NU')
    assert TOKEN_REWARD_PAST.format(reward_amount=round(rewards_total, TOKEN_DECIMAL_PLACE))

    mock_staking_agent.get_current_period.assert_called()
    mock_staking_agent.contract.events[event_name].getLogs.assert_called()


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_show_rewards_not_found(click_runner, surrogate_stakers, mock_staking_agent, mocker):
    event_name = 'Minted'
    event = mocker.Mock()
    event.getLogs = mocker.MagicMock(return_value=[])
    mock_staking_agent.contract.events = {event_name: event}

    command = ('rewards',
               'show',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--staking-address', surrogate_stakers[0],
               '--periods', 10)

    result = click_runner.invoke(stake, command, catch_exceptions=False)
    assert result.exit_code == 0
    assert TOKEN_REWARD_NOT_FOUND in result.output

    mock_staking_agent.get_current_period.assert_called()
    mock_staking_agent.contract.events[event_name].getLogs.assert_called()
