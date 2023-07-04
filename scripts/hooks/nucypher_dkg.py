import random
import sys
import time

import click
import maya
from nucypher_core.ferveo import DkgPublicKey
from web3 import Web3

from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    PREApplicationAgent,
)
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.signers import Signer
from nucypher.characters.lawful import Bob, Enrico
from nucypher.crypto.powers import TransactingPower
from nucypher.policy.conditions.lingo import ConditionLingo
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.logging import GlobalLoggerSettings

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
    type=click.Choice(["tapir", "lynx"]),
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
    type=click.Choice(["mumbai"]),
    default="mumbai",
)
@click.option(
    "--ritual-id",
    "ritual_id",
    "-r",
    help="Ritual ID; existing id or -1 (to initiate a new ritual)",
    type=click.INT,
    required=True,
)
@click.option(
    "--signer",
    "signer_uri",
    "-S",
    help="Signer URI for initializing new ritual",
    default=None,
    type=click.STRING,
)
def nucypher_dkg(
    eth_provider_uri,
    eth_staking_network,
    coordinator_provider_uri,
    coordinator_network,
    ritual_id,
    signer_uri,
):
    if ritual_id < 0 and signer_uri is None:
        raise click.BadOptionUsage(
            option_name="--ritual-id, --signer",
            message=click.style(
                "--signer must be provided when --ritual-id is -1", fg="red"
            ),
        )

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

    #
    # Initial Ritual
    #
    if ritual_id < 0:
        emitter.echo("--------- Initiating Ritual ---------", color="yellow")
        # create account from keystore file
        signer = Signer.from_signer_uri(uri=signer_uri)
        account_address = signer.accounts[0]
        emitter.echo(
            f"Using account {account_address} to initiate DKG Ritual", color="green"
        )

        password = click.prompt(
            "Enter your keystore password", confirmation_prompt=False, hide_input=True
        )
        signer.unlock_account(account=account_address, password=password)
        transacting_power = TransactingPower(signer=signer, account=account_address)

        emitter.echo(
            f"Commencing DKG Ritual on {coordinator_network} using {account_address}",
            color="green",
        )

        # find staking addresses
        _, staking_providers_dict = application_agent.get_all_active_staking_providers()
        staking_providers = list(staking_providers_dict.keys())
        staking_providers.remove(
            "0x7AFDa7e47055CDc597872CA34f9FE75bD083D0Fe"
        )  # TODO skip Bogdan's node; remove at some point

        # sample then sort
        dkg_staking_providers = random.sample(staking_providers, 2)
        dkg_staking_providers.sort()
        emitter.echo(f"Using staking providers for DKG: {dkg_staking_providers}")
        receipt = coordinator_agent.initiate_ritual(
            dkg_staking_providers, transacting_power
        )
        start_ritual_event = (
            coordinator_agent.contract.events.StartRitual().process_receipt(receipt)
        )
        ritual_id = start_ritual_event[0]["args"]["ritualId"]
        ritual_status = coordinator_agent.get_ritual_status(ritual_id)
        assert (
            ritual_status != coordinator_agent.Ritual.Status.NON_INITIATED
        ), "ritual successfully initiated"

        emitter.echo(
            f"DKG Ritual #{ritual_id} initiated: {Web3.to_hex(receipt['transactionHash'])}",
            color="green",
        )

        #
        # Wait for Ritual to complete
        # TODO perhaps reuse EventActuator here
        #
        start_time = maya.now()
        while True:
            ritual_status = coordinator_agent.get_ritual_status(ritual_id)

            if ritual_status == coordinator_agent.Ritual.Status.FINALIZED:
                break

            if (
                ritual_status == coordinator_agent.Ritual.Status.TIMEOUT
                or ritual_status == coordinator_agent.Ritual.Status.INVALID
            ):
                emitter.error(f"Ritual #{ritual_id} failed with status {ritual_status}")
                sys.exit(-1)

            emitter.echo(
                f"Waiting for Ritual to complete; {(maya.now() - start_time).seconds}s elapsed thus far"
            )
            time.sleep(15)

        emitter.echo(
            f"DKG Ritual #{ritual_id} completed after {(maya.now() - start_time).seconds}s",
            color="green",
        )
    else:
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


if __name__ == "__main__":
    nucypher_dkg()
