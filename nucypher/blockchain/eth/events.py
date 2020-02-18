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

from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory


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
            self.timestamp = blockchain.client.w3.eth.getBlock(self.block_number)['timestamp'],

    def __repr__(self):
        pairs_to_show = dict(self.args.items())
        pairs_to_show['block_number'] = self.block_number
        event_str = ", ".join(f"{k}: {v}" for k, v in pairs_to_show.items())
        r = f"({self.__class__.__name__}) {event_str}"
        return r


class ContractEvents:

    def __init__(self, contract):
        self.contract = contract
        self.names = tuple(e.event_name for e in contract.events)

    def __get_web3_event_by_name(self, event_name):
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

            event_filter = event_method.createFilter(fromBlock=from_block,
                                                     toBlock=to_block,
                                                     argument_filters=argument_filters)
            entries = event_filter.get_all_entries()
            for entry in entries:
                yield EventRecord(entry)
        return wrapper

    def __getattr__(self, event_name: str):
        return self[event_name]

    def __iter__(self):
        for event_name in self.names:
            yield self[event_name]