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
from web3 import Web3

from nucypher.blockchain.eth.actors import Staker, StakeHolder
from nucypher.blockchain.eth.constants import MAX_UINT16
from nucypher.blockchain.eth.token import NU, StakeList
from nucypher.cli.actions.select import select_client_account_for_staking
from nucypher.cli.commands.stake import stake, StakeHolderConfigOptions, StakerOptions, TransactingStakerOptions
from nucypher.cli.literature import (
    NO_TOKENS_TO_WITHDRAW, COLLECTING_TOKEN_REWARD, CONFIRM_COLLECTING_WITHOUT_MINTING,
    NO_FEE_TO_WITHDRAW, COLLECTING_ETH_FEE, NO_MINTABLE_PERIODS, STILL_LOCKED_TOKENS, CONFIRM_MINTING,
    PROMPT_PROLONG_VALUE, CONFIRM_PROLONG, SUCCESSFUL_STAKE_PROLONG, PERIOD_ADVANCED_WARNING, PROMPT_STAKE_DIVIDE_VALUE,
    PROMPT_STAKE_EXTEND_VALUE, CONFIRM_BROADCAST_STAKE_DIVIDE, SUCCESSFUL_STAKE_DIVIDE
)
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.types import SubStakeInfo
from tests.constants import MOCK_PROVIDER_URI, YES, INSECURE_DEVELOPMENT_PASSWORD


@pytest.fixture()
def surrogate_staker(mock_testerchain, test_registry, mock_staking_agent):
    address = mock_testerchain.etherbase_account
    staker = Staker(is_me=True, checksum_address=address, registry=test_registry)
    mock_staking_agent.get_all_stakes.return_value = []

    return staker


@pytest.fixture()
def surrogate_stakes(mock_staking_agent, token_economics, surrogate_staker):
    nu = 2 * token_economics.minimum_allowed_locked + 1
    current_period = 10
    duration = token_economics.minimum_locked_periods + 1
    final_period = current_period + duration
    # TODO: Add non divisible, non editable and inactive sub-stakes
    stakes = [SubStakeInfo(current_period - 1, final_period - 1, nu),
              SubStakeInfo(current_period + 1, final_period, nu)]

    mock_staking_agent.get_current_period.return_value = current_period

    def get_all_stakes(staker_address):
        return stakes if staker_address == surrogate_staker.checksum_address else []
    mock_staking_agent.get_all_stakes.side_effect = get_all_stakes

    def get_substake_info(staker_address, stake_index):
        return stakes[stake_index] if staker_address == surrogate_staker.checksum_address else []
    mock_staking_agent.get_substake_info.side_effect = get_substake_info

    return stakes


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
                                       domains={TEMPORARY_DOMAIN},
                                       initial_address=selected_account)
    expected_stakeholder.refresh_stakes()

    staker_options = StakerOptions(config_options=stakeholder_config_options, staking_address=selected_account)
    transacting_staker_options = TransactingStakerOptions(staker_options=staker_options,
                                                          hw_wallet=None,
                                                          beneficiary_address=None,
                                                          allocation_filepath=None)
    stakeholder_from_configuration = transacting_staker_options.create_character(emitter=test_emitter, config_file=None)
    client_account, staking_address = select_client_account_for_staking(emitter=test_emitter,
                                                                        stakeholder=stakeholder_from_configuration,
                                                                        staking_address=selected_account,
                                                                        individual_allocation=None,
                                                                        force=force)
    assert client_account == staking_address == selected_account
    assert stakeholder_from_configuration.stakes == expected_stakeholder.stakes
    assert stakeholder_from_configuration.checksum_address == client_account

    staker_options = StakerOptions(config_options=stakeholder_config_options, staking_address=None)
    transacting_staker_options = TransactingStakerOptions(staker_options=staker_options,
                                                          hw_wallet=None,
                                                          beneficiary_address=None,
                                                          allocation_filepath=None)
    stakeholder_from_configuration = transacting_staker_options.create_character(emitter=None, config_file=None)
    client_account, staking_address = select_client_account_for_staking(emitter=test_emitter,
                                                                        stakeholder=stakeholder_from_configuration,
                                                                        staking_address=selected_account,
                                                                        individual_allocation=None,
                                                                        force=force)
    assert client_account == staking_address == selected_account
    assert stakeholder_from_configuration.stakes == expected_stakeholder.stakes
    assert stakeholder_from_configuration.checksum_address == client_account


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_no_token_reward(click_runner, surrogate_staker, mock_staking_agent):
    # No tokens at all
    mock_staking_agent.calculate_staking_reward.return_value = 0

    collection_args = ('collect-reward',
                       '--no-policy-fee',
                       '--staking-reward',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_staker.checksum_address)

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, collection_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 1
    assert NO_TOKENS_TO_WITHDRAW in result.output

    mock_staking_agent.calculate_staking_reward.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.collect_staking_reward.assert_not_called()
    mock_staking_agent.assert_no_transactions()


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_collecting_token_reward(click_runner, surrogate_staker, mock_staking_agent, mocker):
    mock_mintable_periods = mocker.spy(Staker, 'mintable_periods')

    # Collect some reward
    reward = NU(1, 'NU')
    staked = NU(100, 'NU')
    mock_staking_agent.calculate_staking_reward.return_value = reward.to_nunits()
    mock_staking_agent.non_withdrawable_stake.return_value = staked.to_nunits()

    collection_args = ('collect-reward',
                       '--no-policy-fee',
                       '--staking-reward',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_staker.checksum_address)

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, collection_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert COLLECTING_TOKEN_REWARD.format(reward_amount=reward) in result.output

    mock_staking_agent.calculate_staking_reward.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.collect_staking_reward.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.non_withdrawable_stake.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_mintable_periods.assert_not_called()
    mock_staking_agent.assert_only_transactions([mock_staking_agent.collect_staking_reward])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_collecting_whole_reward_with_warning(click_runner, surrogate_staker, mock_staking_agent, mocker):
    mock_mintable_periods = mocker.spy(Staker, 'mintable_periods')

    # Collect last portion of NU with warning about periods to mint
    reward = NU(1, 'NU')
    mock_staking_agent.calculate_staking_reward.return_value = reward.to_nunits()
    mock_staking_agent.non_withdrawable_stake.return_value = 0
    mock_staking_agent.get_current_period.return_value = 10
    mock_staking_agent.get_current_committed_period.return_value = 8
    mock_staking_agent.get_next_committed_period.return_value = 9

    collection_args = ('collect-reward',
                       '--no-policy-fee',
                       '--staking-reward',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_staker.checksum_address)

    user_input = '\n'.join((INSECURE_DEVELOPMENT_PASSWORD, YES))
    result = click_runner.invoke(stake, collection_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert COLLECTING_TOKEN_REWARD.format(reward_amount=reward) in result.output
    assert CONFIRM_COLLECTING_WITHOUT_MINTING in result.output

    mock_staking_agent.calculate_staking_reward.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.collect_staking_reward.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.non_withdrawable_stake.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.get_current_period.assert_called()
    mock_staking_agent.get_current_committed_period.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.get_next_committed_period.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_mintable_periods.assert_called_once()
    mock_staking_agent.assert_only_transactions([mock_staking_agent.collect_staking_reward])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_collecting_whole_reward_without_warning(click_runner, surrogate_staker, mock_staking_agent, mocker):
    mock_mintable_periods = mocker.spy(Staker, 'mintable_periods')

    # Collect last portion of NU without warning
    reward = NU(1, 'NU')
    mock_staking_agent.calculate_staking_reward.return_value = reward.to_nunits()
    mock_staking_agent.non_withdrawable_stake.return_value = 0
    mock_staking_agent.get_current_committed_period.return_value = 0
    mock_staking_agent.get_next_committed_period.return_value = 0

    collection_args = ('collect-reward',
                       '--no-policy-fee',
                       '--staking-reward',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_staker.checksum_address)

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, collection_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert COLLECTING_TOKEN_REWARD.format(reward_amount=reward) in result.output
    assert CONFIRM_COLLECTING_WITHOUT_MINTING not in result.output

    mock_staking_agent.calculate_staking_reward.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.collect_staking_reward.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.non_withdrawable_stake.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.get_current_period.assert_called()
    mock_staking_agent.get_current_committed_period.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.get_next_committed_period.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_mintable_periods.assert_called_once()
    mock_staking_agent.assert_only_transactions([mock_staking_agent.collect_staking_reward])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_no_policy_fee(click_runner, surrogate_staker, mock_policy_manager_agent):
    mock_policy_manager_agent.get_fee_amount.return_value = 0

    collection_args = ('collect-reward',
                       '--policy-fee',
                       '--no-staking-reward',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_staker.checksum_address)

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, collection_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 1
    assert NO_FEE_TO_WITHDRAW in result.output

    mock_policy_manager_agent.get_fee_amount.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_policy_manager_agent.collect_policy_fee.assert_not_called()
    mock_policy_manager_agent.assert_no_transactions()


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_collecting_fee(click_runner, surrogate_staker, mock_policy_manager_agent):
    fee_amount_eth = 11
    mock_policy_manager_agent.get_fee_amount.return_value = Web3.toWei(fee_amount_eth, 'ether')

    collection_args = ('collect-reward',
                       '--policy-fee',
                       '--no-staking-reward',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_staker.checksum_address)

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, collection_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert COLLECTING_ETH_FEE.format(fee_amount=fee_amount_eth) in result.output

    mock_policy_manager_agent.get_fee_amount.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_policy_manager_agent.collect_policy_fee.assert_called_once()
    mock_policy_manager_agent.assert_only_transactions([mock_policy_manager_agent.collect_policy_fee])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_nothing_to_mint(click_runner, surrogate_staker, mock_staking_agent, mocker):
    mock_mintable_periods = mocker.spy(Staker, 'mintable_periods')
    mock_staking_agent.get_current_committed_period.return_value = 0
    mock_staking_agent.get_next_committed_period.return_value = 0

    mint_command = ('mint',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_staker.checksum_address)

    user_input = INSECURE_DEVELOPMENT_PASSWORD
    result = click_runner.invoke(stake, mint_command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 1
    assert NO_MINTABLE_PERIODS in result.output

    mock_staking_agent.non_withdrawable_stake.assert_not_called()
    mock_staking_agent.get_current_period.assert_called()
    mock_staking_agent.get_current_committed_period.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.get_next_committed_period.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_mintable_periods.assert_called_once()
    mock_staking_agent.assert_no_transactions()


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_mint_with_warning(click_runner, surrogate_staker, mock_staking_agent, mocker):
    mock_mintable_periods = mocker.spy(Staker, 'mintable_periods')
    mock_staking_agent.get_current_period.return_value = 10
    mock_staking_agent.get_current_committed_period.return_value = 9
    mock_staking_agent.get_next_committed_period.return_value = 8
    mock_staking_agent.non_withdrawable_stake.return_value = NU(1, 'NU').to_nunits()

    mint_command = ('mint',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_staker.checksum_address)

    user_input = '\n'.join((INSECURE_DEVELOPMENT_PASSWORD, YES))
    result = click_runner.invoke(stake, mint_command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert STILL_LOCKED_TOKENS in result.output
    assert CONFIRM_MINTING.format(mintable_periods=2) in result.output

    mock_staking_agent.non_withdrawable_stake.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.get_current_period.assert_called()
    mock_staking_agent.get_current_committed_period.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.get_next_committed_period.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_mintable_periods.assert_called_once()
    mock_staking_agent.assert_only_transactions([mock_staking_agent.mint])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_mint_without_warning(click_runner, surrogate_staker, mock_staking_agent, mocker):
    mock_mintable_periods = mocker.spy(Staker, 'mintable_periods')
    mock_staking_agent.get_current_period.return_value = 10
    mock_staking_agent.get_current_committed_period.return_value = 0
    mock_staking_agent.get_next_committed_period.return_value = 8
    mock_staking_agent.non_withdrawable_stake.return_value = 0

    mint_command = ('mint',
                       '--provider', MOCK_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN,
                       '--staking-address', surrogate_staker.checksum_address)

    user_input = '\n'.join((INSECURE_DEVELOPMENT_PASSWORD, YES))
    result = click_runner.invoke(stake, mint_command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert STILL_LOCKED_TOKENS not in result.output
    assert CONFIRM_MINTING.format(mintable_periods=1) in result.output

    mock_staking_agent.non_withdrawable_stake.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.get_current_period.assert_called()
    mock_staking_agent.get_current_committed_period.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_staking_agent.get_next_committed_period.assert_called_once_with(staker_address=surrogate_staker.checksum_address)
    mock_mintable_periods.assert_called_once()
    mock_staking_agent.assert_only_transactions([mock_staking_agent.mint])


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_prolong_interactive(click_runner,
                             mocker,
                             surrogate_staker,
                             surrogate_stakes,
                             mock_staking_agent,
                             token_economics,
                             mock_testerchain):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0
    sub_stake_index = 1
    lock_periods = 10
    final_period = surrogate_stakes[sub_stake_index][1]

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
    mock_staking_agent.prolong_stake.assert_called_once_with(staker_address=surrogate_staker.checksum_address,
                                                             stake_index=sub_stake_index,
                                                             periods=lock_periods)
    mock_staking_agent.assert_only_transactions([mock_staking_agent.prolong_stake])
    mock_staking_agent.get_substake_info.assert_called_once_with(staker_address=surrogate_staker.checksum_address,
                                                                 stake_index=sub_stake_index)


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_prolong_non_interactive(click_runner,
                                 mocker,
                                 surrogate_staker,
                                 surrogate_stakes,
                                 mock_staking_agent,
                                 token_economics,
                                 mock_testerchain):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    sub_stake_index = 1
    lock_periods = 10
    final_period = surrogate_stakes[sub_stake_index][1]

    command = ('prolong',
                '--provider', MOCK_PROVIDER_URI,
                '--network', TEMPORARY_DOMAIN,
                '--staking-address', surrogate_staker.checksum_address,
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
    mock_staking_agent.prolong_stake.assert_called_once_with(staker_address=surrogate_staker.checksum_address,
                                                             stake_index=sub_stake_index,
                                                             periods=lock_periods)
    mock_staking_agent.assert_only_transactions([mock_staking_agent.prolong_stake])
    mock_staking_agent.get_substake_info.assert_called_once_with(staker_address=surrogate_staker.checksum_address,
                                                                 stake_index=sub_stake_index)


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_divide_interactive(click_runner,
                            mocker,
                            surrogate_staker,
                            surrogate_stakes,
                            mock_staking_agent,
                            token_economics,
                            mock_testerchain):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    selected_index = 0
    sub_stake_index = len(surrogate_stakes) - 1
    lock_periods = 10
    min_allowed_locked = token_economics.minimum_allowed_locked
    target_value = min_allowed_locked

    mock_staking_agent.get_worker_from_staker.return_value = surrogate_staker.checksum_address

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
    mock_staking_agent.divide_stake.assert_called_once_with(staker_address=surrogate_staker.checksum_address,
                                                            stake_index=sub_stake_index,
                                                            target_value=target_value,
                                                            periods=lock_periods)
    mock_staking_agent.assert_only_transactions([mock_staking_agent.divide_stake])
    mock_staking_agent.get_substake_info.assert_called_once_with(staker_address=surrogate_staker.checksum_address,
                                                                 stake_index=sub_stake_index)


@pytest.mark.usefixtures("test_registry_source_manager", "patch_stakeholder_configuration")
def test_divide_non_interactive(click_runner,
                                mocker,
                                surrogate_staker,
                                surrogate_stakes,
                                mock_staking_agent,
                                token_economics,
                                mock_testerchain):
    mock_refresh_stakes = mocker.spy(Staker, 'refresh_stakes')

    sub_stake_index = len(surrogate_stakes) - 1
    lock_periods = 10
    min_allowed_locked = token_economics.minimum_allowed_locked
    target_value = min_allowed_locked

    mock_staking_agent.get_worker_from_staker.return_value = surrogate_staker.checksum_address

    command = ('divide',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
                '--staking-address', surrogate_staker.checksum_address,
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
    mock_staking_agent.divide_stake.assert_called_once_with(staker_address=surrogate_staker.checksum_address,
                                                            stake_index=sub_stake_index,
                                                            target_value=target_value,
                                                            periods=lock_periods)
    mock_staking_agent.assert_only_transactions([mock_staking_agent.divide_stake])
    mock_staking_agent.get_substake_info.assert_called_once_with(staker_address=surrogate_staker.checksum_address,
                                                                 stake_index=sub_stake_index)
