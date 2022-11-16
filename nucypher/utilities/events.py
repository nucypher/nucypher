
import csv
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Optional

import maya
from web3.types import BlockIdentifier

from nucypher.blockchain.eth.agents import EthereumContractAgent
from nucypher.blockchain.eth.events import EventRecord


def generate_events_csv_filepath(contract_name: str, event_name: str) -> Path:
    return Path(f'{contract_name}_{event_name}_{maya.now().datetime().strftime("%Y-%m-%d_%H-%M-%S")}.csv')


def write_events_to_csv_file(csv_file: Path,
                             agent: EthereumContractAgent,
                             event_name: str,
                             argument_filters: Dict = None,
                             from_block: Optional[BlockIdentifier] = 0,
                             to_block: Optional[BlockIdentifier] = 'latest') -> bool:
    """
    Write events to csv file.
    :return: True if data written to file, False if there was no event data to write
    """
    event_type = agent.contract.events[event_name]
    entries = event_type.getLogs(fromBlock=from_block, toBlock=to_block, argument_filters=argument_filters)
    if not entries:
        return False

    with open(csv_file, mode='w') as events_file:
        events_writer = None
        for event_record in entries:
            event_record = EventRecord(event_record)
            event_row = OrderedDict()
            event_row['event_name'] = event_name
            event_row['block_number'] = event_record.block_number
            event_row['unix_timestamp'] = event_record.timestamp
            event_row['date'] = maya.MayaDT(event_record.timestamp).iso8601()
            event_row.update(dict(event_record.args.items()))
            if events_writer is None:
                events_writer = csv.DictWriter(events_file, fieldnames=event_row.keys())
                events_writer.writeheader()
            events_writer.writerow(event_row)
    return True
