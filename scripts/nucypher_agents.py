import code
import readline
import rlcompleter

import click

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    SubscriptionManagerAgent,
    TACoApplicationAgent,
    TACoChildApplicationAgent,
)
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.logging import GlobalLoggerSettings

# Get an interactive Python session with all the NuCypher agents loaded by running:
#    python scripts/hooks/nucypher_agents.py [OPTIONS]

GlobalLoggerSettings.start_console_logging()

emitter = StdoutEmitter(verbosity=2)


@click.command()
@click.option(
    "--domain",
    "domain",
    help="TACo domain",
    type=click.Choice(list(domains.SUPPORTED_DOMAINS)),
    default=str(domains.LYNX),
)
@click.option(
    "--eth-endpoint",
    "eth_endpoint",
    help="ETH staking network provider URI",
    type=click.STRING,
    required=True,
)
@click.option(
    "--polygon-endpoint",
    "polygon_endpoint",
    help="Polygon network provider URI",
    type=click.STRING,
    required=True,
)
def nucypher_agents(
    domain,
    eth_endpoint,
    polygon_endpoint,
):
    domain = domains.get_domain(str(domain))
    registry = ContractRegistry.from_latest_publication(domain=domain)
    emitter.echo(f"NOTICE: Connecting to {domain} domain", color="yellow")

    taco_application_agent = ContractAgency.get_agent(
        agent_class=TACoApplicationAgent,
        registry=registry,
        blockchain_endpoint=eth_endpoint,
    )  # type: TACoApplicationAgent

    taco_child_application_agent = ContractAgency.get_agent(
        agent_class=TACoChildApplicationAgent,
        registry=registry,
        blockchain_endpoint=polygon_endpoint,
    )  # type: TACoChildApplicationAgent

    coordinator_agent = ContractAgency.get_agent(
        agent_class=CoordinatorAgent,
        registry=registry,
        blockchain_endpoint=polygon_endpoint,
    )  # type: CoordinatorAgent

    subscription_manager_agent = ContractAgency.get_agent(
        agent_class=SubscriptionManagerAgent,
        registry=registry,
        blockchain_endpoint=polygon_endpoint,
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
