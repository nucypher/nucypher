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

from json.decoder import JSONDecodeError

import json

import os

from typing import Set, Optional, Dict, List

from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.cli.literature import (
    START_LOADING_SEEDNODES,
    NO_DOMAIN_PEERS,
    UNREADABLE_SEEDNODE_ADVISORY,
    SEEDNODE_NOT_STAKING_WARNING
)
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import Teacher
from nucypher.network.teachers import TEACHER_NODES


def load_static_nodes(domains: Set[str], filepath: Optional[str] = None) -> Dict[str, 'Ursula']:
    """
    Non-invasive read teacher-uris from a JSON configuration file keyed by domain name.
    and return a filtered subset of domains and teacher URIs as a dict.
    """

    if not filepath:
        filepath = os.path.join(DEFAULT_CONFIG_ROOT, 'static-nodes.json')
    try:
        with open(filepath, 'r') as file:
            static_nodes = json.load(file)
    except FileNotFoundError:
        return dict()   # No static nodes file, No static nodes.
    except JSONDecodeError:
        raise RuntimeError(f"Static nodes file '{filepath}' contains invalid JSON.")
    filtered_static_nodes = {domain: uris for domain, uris in static_nodes.items() if domain in domains}
    return filtered_static_nodes


def aggregate_seednode_uris(domains: set, highest_priority: Optional[List[str]] = None) -> List[str]:

    # Read from the disk
    static_nodes = load_static_nodes(domains=domains)

    # Priority 1 - URI passed via --teacher
    uris = highest_priority or list()
    for domain in domains:

        # 2 - Static nodes from JSON file
        domain_static_nodes = static_nodes.get(domain)
        if domain_static_nodes:
            uris.extend(domain_static_nodes)

        # 3 - Hardcoded teachers from module
        hardcoded_uris = TEACHER_NODES.get(domain)
        if hardcoded_uris:
            uris.extend(hardcoded_uris)

    return uris


def load_seednodes(emitter,
                   min_stake: int,
                   federated_only: bool,
                   network_domains: set,
                   network_middleware: RestMiddleware = None,
                   teacher_uris: list = None,
                   registry: BaseContractRegistry = None,
                   ) -> List:

    """
    Aggregates seednodes URI sources into a list or teacher URIs ordered
    by connection priority in the following order:

    1. --teacher CLI flag
    2. static-nodes.json
    3. Hardcoded teachers
    """

    # Heads up
    emitter.message(START_LOADING_SEEDNODES, color='yellow')
    from nucypher.characters.lawful import Ursula

    # Aggregate URIs (Ordered by Priority)
    teacher_nodes = list()  # type: List[Ursula]
    teacher_uris = aggregate_seednode_uris(domains=network_domains, highest_priority=teacher_uris)
    if not teacher_uris:
        emitter.message(NO_DOMAIN_PEERS.format(domains=','.join(network_domains)))
        return teacher_nodes

    # Construct Ursulas
    for uri in teacher_uris:
        try:
            teacher_node = Ursula.from_teacher_uri(teacher_uri=uri,
                                                   min_stake=min_stake,
                                                   federated_only=federated_only,
                                                   network_middleware=network_middleware,
                                                   registry=registry)
        except NodeSeemsToBeDown:
            emitter.message(UNREADABLE_SEEDNODE_ADVISORY.format(uri=uri))
            continue
        except Teacher.NotStaking:
            emitter.message(SEEDNODE_NOT_STAKING_WARNING.format(uri=uri))
            continue
        teacher_nodes.append(teacher_node)

    if not teacher_nodes:
        emitter.message(NO_DOMAIN_PEERS.format(domains=','.join(network_domains)))
    return teacher_nodes
