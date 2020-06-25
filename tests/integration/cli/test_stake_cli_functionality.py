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


import random
from unittest.mock import call, patch, PropertyMock

import maya
import pytest
from eth_utils import to_wei
from web3 import Web3

from nucypher.blockchain.eth.actors import Bidder, Staker
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.utils import prettify_eth_amount
from nucypher.cli.commands import worklock as worklock_command
from nucypher.cli.commands.stake import stake
from nucypher.cli.commands.worklock import worklock
from nucypher.cli.literature import (
    BID_AMOUNT_PROMPT_WITH_MIN_BID,
    BID_INCREASE_AMOUNT_PROMPT,
    BIDDING_WINDOW_CLOSED,
    CLAIMING_NOT_AVAILABLE,
    COLLECT_ETH_PASSWORD,
    CONFIRM_BID_VERIFICATION,
    CONFIRM_COLLECT_WORKLOCK_REFUND,
    CONFIRM_REQUEST_WORKLOCK_COMPENSATION,
    CONFIRM_WORKLOCK_CLAIM,
    GENERIC_SELECT_ACCOUNT,
    SELECTED_ACCOUNT,
    WORKLOCK_CLAIM_ADVISORY, NO_TOKENS_TO_WITHDRAW, COLLECTING_TOKEN_REWARD, CONFIRM_COLLECTING_WITHOUT_MINTING,
    NO_FEE_TO_WITHDRAW, COLLECTING_ETH_FEE, NO_MINTABLE_PERIODS, STILL_LOCKED_TOKENS, CONFIRM_MINTING
)
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.types import NuNits
from tests.constants import MOCK_PROVIDER_URI, YES, NO, INSECURE_DEVELOPMENT_PASSWORD
from tests.mock.agents import MockContractAgent


@pytest.fixture()
def surrogate_staker(mock_testerchain, test_registry, mock_staking_agent):
    address = mock_testerchain.etherbase_account
    staker = Staker(is_me=True, checksum_address=address, registry=test_registry)
    mock_staking_agent.get_all_stakes.return_value = []
    return staker


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
