

from json.decoder import JSONDecodeError

import json

import os

from typing import Set, Optional, Dict, List

from nucypher.config.constants import DEFAULT_CONFIG_ROOT


# TODO: This module seems unused

# def load_static_nodes(domains: Set[str], filepath: Optional[str] = None) -> Dict[str, 'Ursula']:
#     """
#     Non-invasive read teacher-uris from a JSON configuration file keyed by domain name.
#     and return a filtered subset of domains and teacher URIs as a dict.
#     """
#
#     if not filepath:
#         filepath = DEFAULT_CONFIG_ROOT / 'static-nodes.json'
#     try:
#         with open(filepath, 'r') as file:
#             static_nodes = json.load(file)
#     except FileNotFoundError:
#         return dict()   # No static nodes file, No static nodes.
#     except JSONDecodeError:
#         raise RuntimeError(f"Static nodes file '{filepath}' contains invalid JSON.")
#     filtered_static_nodes = {domain: uris for domain, uris in static_nodes.items() if domain in domains}
#     return filtered_static_nodes
#
#
#
# def aggregate_seednode_uris(domains: set, highest_priority: Optional[List[str]] = None) -> List[str]:
#
#     # Read from the disk
#     static_nodes = load_static_nodes(domains=domains)
#
#     # Priority 1 - URI passed via --teacher
#     uris = highest_priority or list()
#     for domain in domains:
#
#         # 2 - Static nodes from JSON file
#         domain_static_nodes = static_nodes.get(domain)
#         if domain_static_nodes:
#             uris.extend(domain_static_nodes)
#
#         # 3 - Hardcoded teachers from module
#         hardcoded_uris = TEACHER_NODES.get(domain)
#         if hardcoded_uris:
#             uris.extend(hardcoded_uris)
#
#     return uris
