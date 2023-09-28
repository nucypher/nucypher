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
import code
import readline
import rlcompleter

import click

from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    SubscriptionManagerAgent,
    TACoApplicationAgent,
    TACoChildApplicationAgent,
)
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.logging import GlobalLoggerSettings

# Get an interactive Python session with all the NuCypher agents loaded by running:
#    python scripts/hooks/nucypher_agents.py [OPTIONS]

GlobalLoggerSettings.start_console_logging()

emitter = StdoutEmitter(verbosity=2)


@click.command()
@click.option(
    "--eth-provider",
    "eth_provider_uri",
    help="ETH staking network provider URI",
    type=click.STRING,
    required=True,
)
@click.option(
    "--eth-staking-network",
    "eth_staking_network",
    help="ETH staking network",
    type=click.Choice(NetworksInventory.ETH_NETWORKS),
    default="lynx",
)
@click.option(
    "--coordinator-provider",
    "coordinator_provider_uri",
    help="Coordinator network provider URI",
    type=click.STRING,
    required=True,
)
@click.option(
    "--coordinator-network",
    "coordinator_network",
    help="Coordinator network",
    type=click.Choice(NetworksInventory.POLY_NETWORKS),
    default="mumbai",
)
def nucypher_agents(
    eth_provider_uri,
    eth_staking_network,
    coordinator_provider_uri,
    coordinator_network,
):
    staking_registry = InMemoryContractRegistry.from_latest_publication(
        network=eth_staking_network
    )
    emitter.echo(f"NOTICE: Connecting to {eth_staking_network} network", color="yellow")

    taco_application_agent = ContractAgency.get_agent(
        agent_class=TACoApplicationAgent,
        registry=staking_registry,
        provider_uri=eth_provider_uri,
    )  # type: TACoApplicationAgent

    coordinator_network_registry = InMemoryContractRegistry.from_latest_publication(
        network=coordinator_network
    )
    emitter.echo(f"NOTICE: Connecting to {coordinator_network} network", color="yellow")

    taco_child_application_agent = ContractAgency.get_agent(
        agent_class=TACoChildApplicationAgent,
        registry=coordinator_network_registry,
        provider_uri=coordinator_provider_uri,
    )  # type: TACoChildApplicationAgent

    coordinator_agent = ContractAgency.get_agent(
        agent_class=CoordinatorAgent,
        registry=coordinator_network_registry,
        provider_uri=coordinator_provider_uri,
    )  # type: CoordinatorAgent

    subscription_manager_agent = ContractAgency.get_agent(
        agent_class=SubscriptionManagerAgent,
        registry=coordinator_network_registry,
        provider_uri=coordinator_provider_uri,
    )  # type: SubscriptionManagerAgent

    message = (
        "TACo agents pre-loaded in variables:\n"
        "\t'taco_application_agent'\n"
        "\t'taco_child_application_agent'\n"
        "\t'coordinator_agent'\n"
        "\t'subscription_manager_agent'"
    )
    emitter.echo(message=message, color="green")

    # set up auto-completion
    readline.set_completer(rlcompleter.Completer(locals()).complete)
    readline.parse_and_bind("tab: complete")

    # start interactive shell
    code.interact(local=locals())


if __name__ == "__main__":
    nucypher_agents()
