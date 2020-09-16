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
import maya
from eth_typing import BlockNumber
from unittest.mock import patch

from nucypher.blockchain.eth.constants import AVERAGE_BLOCK_TIME_IN_SECONDS
from nucypher.blockchain.eth.utils import epoch_to_period, estimate_block_number_for_period, period_to_epoch

SECONDS_PER_PERIOD = 60 * 60 * 24


def test_epoch_to_period():
    timestamp = maya.now().epoch

    current_period = epoch_to_period(epoch=timestamp, seconds_per_period=SECONDS_PER_PERIOD)
    assert current_period == (timestamp // SECONDS_PER_PERIOD)


def test_period_to_epoch():
    current_period = 12345678
    epoch = period_to_epoch(period=current_period, seconds_per_period=SECONDS_PER_PERIOD)
    assert epoch == (current_period * SECONDS_PER_PERIOD)


def test_estimate_block_number_for_period():
    timestamp = maya.now().epoch
    period = timestamp // SECONDS_PER_PERIOD

    three_periods_back = period - 3
    ten_periods_back = period - 10
    latest_block_number = BlockNumber(12345678)

    now = maya.now()
    now_epoch = now.epoch
    # ensure the same time is used in method and in test
    with patch.object(maya, 'now', return_value=maya.MayaDT(epoch=now_epoch)):
        block_number_for_three_periods_back = estimate_block_number_for_period(period=three_periods_back,
                                                                               seconds_per_period=SECONDS_PER_PERIOD,
                                                                               latest_block=latest_block_number)
        block_number_for_ten_periods_back = estimate_block_number_for_period(period=ten_periods_back,
                                                                             seconds_per_period=SECONDS_PER_PERIOD,
                                                                             latest_block=latest_block_number)

    for past_period, block_number_for_past_period in ((three_periods_back, block_number_for_three_periods_back),
                                                      (ten_periods_back, block_number_for_ten_periods_back)):
        start_of_past_period = maya.MayaDT(epoch=(past_period * SECONDS_PER_PERIOD))
        diff_in_seconds = int((now - start_of_past_period).total_seconds())
        diff_in_blocks = diff_in_seconds // AVERAGE_BLOCK_TIME_IN_SECONDS

        assert block_number_for_past_period < latest_block_number
        assert block_number_for_past_period == (latest_block_number - diff_in_blocks)
