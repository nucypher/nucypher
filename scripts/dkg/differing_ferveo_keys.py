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

from typing import List, Optional

import click
import requests
from eth_typing import ChecksumAddress
from nucypher_core import NodeMetadata
from urllib3.exceptions import InsecureRequestWarning

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
)
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.logging import GlobalLoggerSettings

# Get an interactive Python session with all the NuCypher agents loaded by running:
#    python scripts/hooks/nucypher_agents.py [OPTIONS]

GlobalLoggerSettings.start_console_logging()

emitter = StdoutEmitter(verbosity=2)


def get_node_urls(participants: Optional[List[ChecksumAddress]] = None):
    participants_set = set(participants) if participants else None
    node_urls = {}
    try:
        response = requests.get(
            "https://mainnet.nucypher.network:9151/status?json=true",
            verify=False,
            timeout=5,
        )
        all_nodes = response.json().get("known_nodes", [])
        for node in all_nodes:
            staker_address = node["staker_address"]
            if participants_set and staker_address not in participants_set:
                continue
            node_urls[node["staker_address"]] = f"https://{node['rest_url']}"
    except Exception:
        pass

    return node_urls


def get_current_ferveo_key(node_url):
    try:
        response = requests.get(
            f"{node_url}/public_information", verify=False, timeout=5
        )
        node_metadata = NodeMetadata.from_bytes(response.content)
        return node_metadata.payload.ferveo_public_key
    except Exception:
        pass

    return None


@click.command()
@click.option(
    "--polygon-endpoint",
    "polygon_endpoint",
    help="Polygon network provider URI",
    type=click.STRING,
    required=True,
)
@click.option(
    "--ritual-id", help="Ritual ID", type=click.INT, required=False, default=None
)
def differing_ferveo_keys(
    polygon_endpoint,
    ritual_id,
):
    # Suppress https verification warnings
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

    domain = domains.get_domain(domains.MAINNET.name)
    registry = ContractRegistry.from_latest_publication(domain=domain)
    emitter.echo(f"NOTICE: Connecting to {domain} domain", color="yellow")

    coordinator_agent = ContractAgency.get_agent(
        agent_class=CoordinatorAgent,
        registry=registry,
        blockchain_endpoint=polygon_endpoint,
    )  # type: CoordinatorAgent

    participants = None  # None means all nodes
    if ritual_id:
        ritual = coordinator_agent.get_ritual(ritual_id)
        participants = ritual.providers  # only nodes for ritual

    node_urls = get_node_urls(participants)
    ritual_id_for_public_key_check = ritual_id or coordinator_agent.number_of_rituals()
    for provider, node_url in node_urls.items():
        if not node_url:
            print(f"Unable to determine public ip for {provider}")
            continue
        else:
            current_ferveo_key = get_current_ferveo_key(node_url)
            if not current_ferveo_key:
                print(
                    f"Unable to obtain current public key from {node_url} for {provider}"
                )
                continue

        reported_ferveo_key = coordinator_agent.get_provider_public_key(
            provider, ritual_id_for_public_key_check
        )

        if bytes(current_ferveo_key) != bytes(reported_ferveo_key):
            print(f"[MISMATCH] {provider} is using different key than reported")


if __name__ == "__main__":
    differing_ferveo_keys()
