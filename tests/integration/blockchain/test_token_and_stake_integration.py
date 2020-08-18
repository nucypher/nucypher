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

from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.token import NU, Stake, validate_divide, validate_prolong, validate_increase, \
    validate_merge
from nucypher.types import StakerInfo


def test_child_status():
    for status in Stake.Status:
        assert status.is_child(status)

    # Check relations for inactive status
    assert Stake.Status.INACTIVE.is_child(Stake.Status.UNLOCKED)
    assert not Stake.Status.INACTIVE.is_child(Stake.Status.LOCKED)
    assert not Stake.Status.INACTIVE.is_child(Stake.Status.EDITABLE)
    assert not Stake.Status.INACTIVE.is_child(Stake.Status.DIVISIBLE)

    # Check relations for unlocked status
    assert not Stake.Status.UNLOCKED.is_child(Stake.Status.INACTIVE)
    assert not Stake.Status.UNLOCKED.is_child(Stake.Status.LOCKED)
    assert not Stake.Status.UNLOCKED.is_child(Stake.Status.EDITABLE)
    assert not Stake.Status.UNLOCKED.is_child(Stake.Status.DIVISIBLE)

    # Check relations for locked status
    assert not Stake.Status.LOCKED.is_child(Stake.Status.INACTIVE)
    assert not Stake.Status.LOCKED.is_child(Stake.Status.UNLOCKED)
    assert not Stake.Status.LOCKED.is_child(Stake.Status.EDITABLE)
    assert not Stake.Status.LOCKED.is_child(Stake.Status.DIVISIBLE)

    # Check relations for editable status
    assert not Stake.Status.EDITABLE.is_child(Stake.Status.INACTIVE)
    assert not Stake.Status.EDITABLE.is_child(Stake.Status.UNLOCKED)
    assert Stake.Status.EDITABLE.is_child(Stake.Status.LOCKED)
    assert not Stake.Status.EDITABLE.is_child(Stake.Status.DIVISIBLE)

    # Check relations for divisible status
    assert not Stake.Status.DIVISIBLE.is_child(Stake.Status.INACTIVE)
    assert not Stake.Status.DIVISIBLE.is_child(Stake.Status.UNLOCKED)
    assert Stake.Status.DIVISIBLE.is_child(Stake.Status.LOCKED)
    assert Stake.Status.DIVISIBLE.is_child(Stake.Status.EDITABLE)


def test_stake_status(mock_testerchain, token_economics, mock_staking_agent):

    address = mock_testerchain.etherbase_account
    current_period = 3
    staker_info = StakerInfo(current_committed_period=current_period-1,
                             next_committed_period=current_period,
                             value=0,
                             last_committed_period=0,
                             lock_restake_until_period=False,
                             completed_work=0,
                             worker_start_period=0,
                             worker=NULL_ADDRESS,
                             flags=bytes())

    mock_staking_agent.get_current_period.return_value = current_period
    mock_staking_agent.get_staker_info.return_value = staker_info

    def make_sub_stake(value, first_locked_period, final_locked_period):
        return Stake(checksum_address=address,
                     first_locked_period=first_locked_period,
                     final_locked_period=final_locked_period,
                     value=value,
                     index=0,
                     staking_agent=mock_staking_agent,
                     economics=token_economics)

    # Prepare unlocked sub-stake
    nu = NU.from_nunits(2 * token_economics.minimum_allowed_locked - 1)
    stake = make_sub_stake(nu, current_period - 2, current_period - 1)
    assert stake.status() == Stake.Status.UNLOCKED

    # Prepare inactive sub-stake
    # Update staker info and create new state
    stake = make_sub_stake(nu, current_period - 2, current_period - 1)

    staker_info = staker_info._replace(current_committed_period=current_period,
                                       next_committed_period=current_period + 1)
    mock_staking_agent.get_staker_info.return_value = staker_info

    assert stake.status() == Stake.Status.INACTIVE

    # Prepare locked sub-stake
    stake = make_sub_stake(nu, current_period - 2, current_period)
    assert stake.status() == Stake.Status.LOCKED

    # Prepare editable sub-stake
    stake = make_sub_stake(nu, current_period - 2, current_period + 1)
    assert stake.status() == Stake.Status.EDITABLE

    # Prepare divisible sub-stake
    nu = NU.from_nunits(2 * token_economics.minimum_allowed_locked)
    stake = make_sub_stake(nu, current_period - 2, current_period + 1)
    assert stake.status() == Stake.Status.DIVISIBLE


def test_stake_sync(mock_testerchain, token_economics, mock_staking_agent):

    address = mock_testerchain.etherbase_account
    current_period = 3
    staker_info = StakerInfo(current_committed_period=current_period-1,
                             next_committed_period=current_period,
                             value=0,
                             last_committed_period=0,
                             lock_restake_until_period=False,
                             completed_work=0,
                             worker_start_period=0,
                             worker=NULL_ADDRESS,
                             flags=bytes())

    mock_staking_agent.get_current_period.return_value = current_period
    mock_staking_agent.get_staker_info.return_value = staker_info

    # Prepare sub-stake
    nu = NU.from_nunits(2 * token_economics.minimum_allowed_locked - 1)
    stake = Stake(checksum_address=address,
                  first_locked_period=current_period - 2,
                  final_locked_period=current_period + 1,
                  value=nu,
                  index=0,
                  staking_agent=mock_staking_agent,
                  economics=token_economics)
    assert stake.status() == Stake.Status.EDITABLE

    # Update locked value and sync
    sub_stake_info = stake.to_stake_info()
    nunits = 2 * token_economics.minimum_allowed_locked
    sub_stake_info = sub_stake_info._replace(locked_value=nunits)
    mock_staking_agent.get_substake_info.return_value = sub_stake_info

    stake.sync()
    assert stake.status() == Stake.Status.DIVISIBLE
    assert stake.value == NU.from_nunits(nunits)

    # Update current period and sync
    mock_staking_agent.get_current_period.return_value = current_period + 1
    sub_stake_info = sub_stake_info._replace(locked_value=nunits)
    mock_staking_agent.get_substake_info.return_value = sub_stake_info

    stake.sync()
    assert stake.status() == Stake.Status.LOCKED
    assert stake.final_locked_period == current_period + 1

    # Update final period and sync
    sub_stake_info = sub_stake_info._replace(last_period=current_period)
    mock_staking_agent.get_substake_info.return_value = sub_stake_info

    stake.sync()
    assert stake.status() == Stake.Status.UNLOCKED
    assert stake.final_locked_period == current_period

    # Update first period and sync
    sub_stake_info = sub_stake_info._replace(first_period=current_period)
    mock_staking_agent.get_substake_info.return_value = sub_stake_info

    with pytest.raises(Stake.StakingError):
        stake.sync()


def test_stake_validation(mock_testerchain, token_economics, mock_staking_agent):

    address = mock_testerchain.etherbase_account

    # Validate stake initialization
    with pytest.raises(Stake.StakingError):
        Stake.initialize_stake(staking_agent=mock_staking_agent,
                               checksum_address=address,
                               economics=token_economics,
                               amount=token_economics.minimum_allowed_locked - 1,
                               lock_periods=token_economics.minimum_locked_periods)

    with pytest.raises(Stake.StakingError):
        Stake.initialize_stake(staking_agent=mock_staking_agent,
                               checksum_address=address,
                               economics=token_economics,
                               amount=token_economics.minimum_allowed_locked,
                               lock_periods=token_economics.minimum_locked_periods - 1)

    with pytest.raises(Stake.StakingError):
        Stake.initialize_stake(staking_agent=mock_staking_agent,
                               checksum_address=address,
                               economics=token_economics,
                               amount=token_economics.maximum_allowed_locked + 1,
                               lock_periods=token_economics.minimum_locked_periods)

    mock_staking_agent.get_locked_tokens.return_value = 0
    Stake.initialize_stake(staking_agent=mock_staking_agent,
                           checksum_address=address,
                           economics=token_economics,
                           amount=token_economics.maximum_allowed_locked,
                           lock_periods=token_economics.minimum_locked_periods)

    # Validate divide method
    current_period = 10
    mock_staking_agent.get_current_period.return_value = 10

    def make_sub_stake(value, first_locked_period, final_locked_period, index=0):
        return Stake(checksum_address=address,
                     first_locked_period=first_locked_period,
                     final_locked_period=final_locked_period,
                     value=value,
                     index=index,
                     staking_agent=mock_staking_agent,
                     economics=token_economics)

    nu = NU.from_nunits(2 * token_economics.minimum_allowed_locked - 1)
    stake = make_sub_stake(first_locked_period=current_period - 2,
                           final_locked_period=current_period + 1,
                           value=nu)

    with pytest.raises(Stake.StakingError):
        validate_divide(stake=stake, target_value=token_economics.minimum_allowed_locked, additional_periods=1)

    stake = make_sub_stake(first_locked_period=current_period - 2,
                           final_locked_period=current_period,
                           value=nu + 1)
    with pytest.raises(Stake.StakingError):
        validate_divide(stake=stake, target_value=token_economics.minimum_allowed_locked, additional_periods=1)

    stake = make_sub_stake(first_locked_period=current_period - 2,
                           final_locked_period=current_period + 1,
                           value=nu + 1)
    with pytest.raises(Stake.StakingError):
        validate_divide(stake=stake, target_value=token_economics.minimum_allowed_locked - 1, additional_periods=1)
    validate_divide(stake=stake, target_value=token_economics.minimum_allowed_locked, additional_periods=1)

    # Validate prolong method
    stake = make_sub_stake(first_locked_period=current_period - 2,
                           final_locked_period=current_period,
                           value=nu)
    with pytest.raises(Stake.StakingError):
        validate_prolong(stake=stake, additional_periods=1)

    stake = make_sub_stake(first_locked_period=current_period - 2,
                           final_locked_period=current_period + 10,
                           value=nu)
    with pytest.raises(Stake.StakingError):
        validate_prolong(stake=stake, additional_periods=1)
    with pytest.raises(Stake.StakingError):
        validate_prolong(stake=stake, additional_periods=token_economics.minimum_locked_periods - 11)
    validate_prolong(stake=stake, additional_periods=token_economics.minimum_locked_periods - 10)

    # Validate increase method
    stake = make_sub_stake(first_locked_period=current_period - 2,
                           final_locked_period=current_period,
                           value=nu)
    with pytest.raises(Stake.StakingError):
        validate_increase(stake=stake, amount=nu)

    stake = make_sub_stake(first_locked_period=current_period - 2,
                           final_locked_period=current_period + 1,
                           value=nu)
    stake.staking_agent.get_locked_tokens.return_value = nu
    with pytest.raises(Stake.StakingError):
        validate_increase(stake=stake, amount=NU.from_nunits(token_economics.maximum_allowed_locked - int(nu) + 1))
    validate_increase(stake=stake, amount=NU.from_nunits(token_economics.maximum_allowed_locked - int(nu)))

    # Validate merge method
    stake_1 = make_sub_stake(first_locked_period=current_period - 1,
                             final_locked_period=current_period,
                             value=nu,
                             index=0)
    stake_2 = make_sub_stake(first_locked_period=current_period - 1,
                             final_locked_period=current_period,
                             value=nu,
                             index=1)
    with pytest.raises(Stake.StakingError):
        validate_merge(stake_1=stake_1, stake_2=stake_2)

    stake_1 = make_sub_stake(first_locked_period=current_period - 1,
                             final_locked_period=current_period + 1,
                             value=nu,
                             index=2)
    stake_2 = make_sub_stake(first_locked_period=current_period - 1,
                             final_locked_period=current_period + 2,
                             value=nu,
                             index=3)
    with pytest.raises(Stake.StakingError):
        validate_merge(stake_1=stake_1, stake_2=stake_2)
    with pytest.raises(Stake.StakingError):
        validate_merge(stake_1=stake_1, stake_2=stake_1)

    stake_2 = make_sub_stake(first_locked_period=current_period - 3,
                             final_locked_period=current_period + 1,
                             value=nu,
                             index=4)
    validate_merge(stake_1=stake_1, stake_2=stake_2)
