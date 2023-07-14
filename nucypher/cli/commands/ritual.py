import click
from nucypher_core.ferveo import DkgPublicKey

from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    PREApplicationAgent,
)
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.characters.lawful import Bob, Enrico
from nucypher.cli.options import option_eth_provider_uri
from nucypher.cli.types import NuCypherNetworkName
from nucypher.policy.conditions.lingo import ConditionLingo
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.logging import GlobalLoggerSettings

GlobalLoggerSettings.start_console_logging()
emitter = StdoutEmitter(verbosity=2)


option_eth_staking_network = click.option(
    "--eth-staking-network",
    "eth_staking_network",
    help="ETH staking network",
    type=NuCypherNetworkName(validate=True),
    # TODO no default value provided for now; should the default be "mainnet"?
    required=True,
)

option_coordinator_provider = click.option(
    "--coordinator-provider",
    "coordinator_provider_uri",
    help="Coordinator network provider URI",
    type=click.STRING,
    required=True,
)

option_coordinator_network = click.option(
    "--coordinator-network",
    "coordinator_network",
    help="Coordinator network",
    type=click.Choice(NetworksInventory.POLY_NETWORKS),
    # TODO no default value provided for now; should the default be "polygon"?
    required=True,
)


def get_agency(
    coordinator_network, coordinator_provider_uri, eth_staking_network, eth_provider_uri
):
    coordinator_agent = ContractAgency.get_agent(
        agent_class=CoordinatorAgent,
        registry=InMemoryContractRegistry.from_latest_publication(
            network=coordinator_network
        ),
        provider_uri=coordinator_provider_uri,
    )  # type: CoordinatorAgent

    staking_network_registry = InMemoryContractRegistry.from_latest_publication(
        network=eth_staking_network
    )
    application_agent = ContractAgency.get_agent(
        agent_class=PREApplicationAgent,
        registry=staking_network_registry,
        provider_uri=eth_provider_uri,
    )  # type: PREApplicationAgent

    return coordinator_agent, application_agent, staking_network_registry


@click.group()
def ritual():
    """Ritual management commands"""


@ritual.command()
@option_eth_provider_uri(required=True)
@option_eth_staking_network
@option_coordinator_provider
@option_coordinator_network
@click.option(
    "--ritual-id",
    "ritual_id",
    "-r",
    help="Ritual ID; defaults to -1 to initiate a new ritual",
    type=click.INT,
    required=True,
)
def check(
    eth_provider_uri: str,
    eth_staking_network: str,
    coordinator_provider_uri: str,
    coordinator_network: str,
    ritual_id: int,
):
    coordinator_agent, application_agent, staking_network_registry = get_agency(
        coordinator_network,
        coordinator_provider_uri,
        eth_staking_network,
        eth_provider_uri,
    )

    # ensure ritual exists
    _ = coordinator_agent.get_ritual(ritual_id)  # ensure ritual can be found
    emitter.echo(f"Reusing existing DKG Ritual #{ritual_id}", color="green")

    #
    # Encrypt some data
    #

    emitter.echo("--------- Data Encryption ---------")

    PLAINTEXT = """
    Those who mistake the unessential to be essential and the essential to be unessential,
    dwelling in wrong thoughts, never arrive at the essential.
    
    Those who know the essential to be essential and the unessential to be unessential,
    dwelling in right thoughts, do arrive at the essential.
    """
    # -- Dhammapada

    CONDITIONS = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "returnValueTest": {"value": "0", "comparator": ">"},
            "method": "blocktime",
            "chain": application_agent.blockchain.client.chain_id,
        },
    }

    encrypting_key = DkgPublicKey.from_bytes(
        bytes(coordinator_agent.get_ritual(ritual_id).public_key)
    )

    enrico = Enrico(encrypting_key=encrypting_key)
    ciphertext = enrico.encrypt_for_dkg(
        plaintext=PLAINTEXT.encode(), conditions=CONDITIONS
    )

    emitter.echo("-- Data encrypted --", color="green")

    #
    # Get Data Decrypted
    #
    emitter.echo("--------- Threshold Decryption ---------")
    bob = Bob(
        eth_provider_uri=eth_provider_uri,
        domain=eth_staking_network,
        registry=staking_network_registry,
        coordinator_network=coordinator_network,
        coordinator_provider_uri=coordinator_provider_uri,
    )
    bob.start_learning_loop(now=True)

    cleartext = bob.threshold_decrypt(
        ritual_id=ritual_id,
        ciphertext=ciphertext,
        conditions=CONDITIONS,
    )

    emitter.echo(f"\n-- Data decrypted -- \n{bytes(cleartext).decode()}", color="green")
    assert bytes(cleartext).decode() == PLAINTEXT
