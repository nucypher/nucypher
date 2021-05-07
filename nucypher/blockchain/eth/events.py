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
import os

from web3.contract import Contract

from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.config.constants import NUCYPHER_EVENTS_THROTTLE_MAX_BLOCKS


class EventRecord:
    def __init__(self, event: dict):
        self.raw_event = dict(event)
        self.args = dict(event['args'])
        self.block_number = event['blockNumber']
        self.transaction_hash = event['transactionHash'].hex()

        try:
            blockchain = BlockchainInterfaceFactory.get_interface()
        except BlockchainInterfaceFactory.NoRegisteredInterfaces:
            self.timestamp = None
        else:
            self.timestamp = blockchain.client.w3.eth.getBlock(self.block_number)['timestamp']

    def __repr__(self):
        pairs_to_show = dict(self.args.items())
        pairs_to_show['block_number'] = self.block_number
        event_str = ", ".join(f"{k}: {v}" for k, v in pairs_to_show.items())
        r = f"({self.__class__.__name__}) {event_str}"
        return r


class ContractEvents:

    def __init__(self, contract: Contract):
        self.contract = contract
        self.names = tuple(e.event_name for e in contract.events)

    def __get_web3_event_by_name(self, event_name: str):
        if event_name not in self.names:
            raise TypeError(f"Event '{event_name}' doesn't exist in this contract. Valid events are {self.names}")
        event_method = getattr(self.contract.events, event_name)
        return event_method

    def __getitem__(self, event_name: str):
        event_method = self.__get_web3_event_by_name(event_name)

        def wrapper(from_block=None, to_block=None, **argument_filters):

            if from_block is None:
                from_block = 0  # TODO: we can do better. Get contract creation block.
            if to_block is None:
                to_block = 'latest'

            entries = event_method.getLogs(fromBlock=from_block, toBlock=to_block, argument_filters=argument_filters)
            for entry in entries:
                yield EventRecord(entry)
        return wrapper

    def __getattr__(self, event_name: str):
        return self[event_name]

    def __iter__(self):
        for event_name in self.names:
            yield self[event_name]


class ContractEventsThrottler:
    """
    Enables Contract events to be retrieved in batches.
    """
    # default to 1000 - smallest default heard about so far (alchemy)
    DEFAULT_MAX_BLOCKS_PER_CALL = int(os.environ.get(NUCYPHER_EVENTS_THROTTLE_MAX_BLOCKS, 1000))

    def __init__(self,
                 agent: 'EthereumContractAgent',
                 event_name: str,
                 from_block: int,
                 to_block: int = None,  # defaults to latest block
                 max_blocks_per_call: int = DEFAULT_MAX_BLOCKS_PER_CALL,
                 **argument_filters):
        self.event_filter = agent.events[event_name]
        self.from_block = from_block
        self.to_block = to_block if to_block is not None else agent.blockchain.client.block_number
        # validity check of block range
        if self.to_block < self.from_block:
            raise ValueError(f"Invalid events block range: to_block {self.to_block} must be greater than or equal "
                             f"to from_block {self.from_block}")

        self.max_blocks_per_call = max_blocks_per_call
        self.argument_filters = argument_filters

    def __iter__(self):
        current_from_block = self.from_block
        current_to_block = min(self.from_block + self.max_blocks_per_call, self.to_block)
        while current_from_block <= current_to_block:
            for event_record in self.event_filter(from_block=current_from_block,
                                                  to_block=current_to_block,
                                                  **self.argument_filters):
                yield event_record
            # previous block range is inclusive hence the increment
            current_from_block = current_to_block + 1
            # update the 'to block' to the lesser of either the next `max_blocks_per_call` blocks,
            # or the remainder of blocks
            current_to_block = min(current_from_block + self.max_blocks_per_call, self.to_block)
