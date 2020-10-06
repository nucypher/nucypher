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

from unittest.mock import Mock, MagicMock

import pytest

from nucypher.blockchain.eth.events import ContractEventsThrottler


def test_contract_events_throttler_to_block_check():
    event_name = 'TestEvent'
    latest_block = 50
    blockchain = MagicMock()
    blockchain.client.block_number = latest_block
    agent = Mock(events={event_name: Mock(return_value=[])}, blockchain=blockchain)

    # from_block < to_block
    throttler = ContractEventsThrottler(agent=agent, event_name=event_name, from_block=1, to_block=10)
    assert throttler.from_block == 1
    assert throttler.to_block == 10

    # to_block < from_block
    with pytest.raises(ValueError):
        ContractEventsThrottler(agent=agent, event_name=event_name, from_block=10, to_block=8)

    # to_block can be equal to from_block
    throttler = ContractEventsThrottler(agent=agent, event_name=event_name, from_block=10, to_block=10)
    assert throttler.from_block == 10
    assert throttler.to_block == 10

    # from_block and to_block value of zero allowed
    throttler = ContractEventsThrottler(agent=agent, event_name=event_name, from_block=0, to_block=0)
    assert throttler.from_block == 0
    assert throttler.to_block == 0

    #
    # when to_block is not specified it defaults to latest block number
    #

    # latest block is lower than from_block
    with pytest.raises(ValueError):
        ContractEventsThrottler(agent=agent, event_name=event_name, from_block=latest_block + 1)

    # latest block is equal to from_block
    throttler = ContractEventsThrottler(agent=agent, event_name=event_name, from_block=latest_block)
    assert throttler.from_block == latest_block
    assert throttler.to_block == latest_block


def test_contract_events_throttler_inclusive_block_ranges():
    event_name = 'TestEvent'

    #
    # 1 block at a time
    #
    mock_method = Mock(return_value=[])
    agent = Mock(events={event_name: mock_method})
    events_throttler = ContractEventsThrottler(
        agent=agent,
        event_name=event_name,
        from_block=0,
        to_block=10,
        max_blocks_per_call=1
    )

    for _ in events_throttler:
        pass

    # check calls to filter
    # ranges used = (0, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 10)
    assert mock_method.call_count == 6
    mock_method.assert_any_call(from_block=0, to_block=1)
    mock_method.assert_any_call(from_block=2, to_block=3)
    mock_method.assert_any_call(from_block=4, to_block=5)
    mock_method.assert_any_call(from_block=6, to_block=7)
    mock_method.assert_any_call(from_block=8, to_block=9)
    mock_method.assert_any_call(from_block=10, to_block=10)

    #
    # 5 blocks at a time
    #
    mock_method = Mock(return_value=[])
    agent = Mock(events={event_name: mock_method})
    argument_filters = {'address': '0xdeadbeef'}
    events_throttler = ContractEventsThrottler(
        agent=agent,
        event_name=event_name,
        from_block=0,
        to_block=21,
        max_blocks_per_call=5,
        **argument_filters
    )

    for _ in events_throttler:
        pass

    # check calls to filter
    # ranges used = (0, 5), (6, 11), (12, 17) (18, 21)
    assert mock_method.call_count == 4
    mock_method.assert_any_call(**argument_filters, from_block=0, to_block=5)
    mock_method.assert_any_call(**argument_filters, from_block=6, to_block=11)
    mock_method.assert_any_call(**argument_filters, from_block=12, to_block=17)
    mock_method.assert_any_call(**argument_filters, from_block=18, to_block=21)
