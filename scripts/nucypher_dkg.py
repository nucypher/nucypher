import random
import time

import click
import maya
from nucypher_core.ferveo import DkgPublicKey
from web3 import Web3

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    TACoChildApplicationAgent,
)
from nucypher.blockchain.eth.models import Coordinator
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.blockchain.eth.signers import InMemorySigner, Signer
from nucypher.characters.lawful import Bob, Enrico
from nucypher.crypto.powers import TransactingPower
from nucypher.policy.conditions.lingo import ConditionLingo, ConditionType
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.logging import GlobalLoggerSettings
from tests.constants import DEFAULT_TEST_ENRICO_PRIVATE_KEY, GLOBAL_ALLOW_LIST

GlobalLoggerSettings.start_console_logging()

emitter = StdoutEmitter(verbosity=2)


def get_transacting_power(signer: Signer):
    account_address = signer.accounts[0]
    emitter.echo(
        f"Using {account_address} for initiation/authorization for DKG Ritual",
        color="green",
    )

    password = click.prompt(
        "Enter your keystore password", confirmation_prompt=False, hide_input=True
    )
    signer.unlock_account(account=account_address, password=password)
    transacting_power = TransactingPower(signer=signer, account=account_address)

    return transacting_power


@click.command()
@click.option(
    "--domain",
    "domain",
    help="TACo Domain",
    type=click.Choice([str(domains.TAPIR), str(domains.LYNX)]),
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
@click.option(
    "--ritual-id",
    "ritual_id",
    "-r",
    help="Ritual ID; defaults to -1 to initiate a new ritual",
    type=click.INT,
    default=-1,
    required=True,
)
@click.option(
    "--signer",
    "signer_uri",
    "-S",
    help="Signer URI for initiating a new ritual with Coordinator contract",
    default=None,
    type=click.STRING,
)
@click.option(
    "--dkg-size",
    "dkg_size",
    "-n",
    help="Number of nodes to participate in ritual",
    type=click.INT,
    default=0,
)
@click.option(
    "--num-rituals",
    "num_rituals",
    help="The number of rituals to initiate",
    type=click.INT,
    default=1,
)
@click.option(
    "--ritual-duration",
    "ritual_duration",
    help="The duration (in seconds) for initialized ritual(s)",
    type=click.INT,
    default=60 * 60 * 24,  # 24 hours
)
@click.option(
    "--use-random-enrico",
    "use_random_enrico",
    help="Use a random Enrico signing account vs using a known default Enrico signing account (default)",
    is_flag=True,
    default=False,
)
@click.option(
    "--access-controller",
    "-a",
    help=f"'{GLOBAL_ALLOW_LIST}' or 'OpenAccessAuthorizer' contract",
    type=click.Choice([GLOBAL_ALLOW_LIST, "OpenAccessAuthorizer"]),
    required=False,
)
def nucypher_dkg(
    domain,
    eth_endpoint,
    polygon_endpoint,
    ritual_id,
    signer_uri,
    dkg_size,
    num_rituals,
    ritual_duration,
    use_random_enrico,
    access_controller,
):
    if ritual_id < 0:
        # if creating ritual(s)
        if signer_uri is None:
            raise click.BadOptionUsage(
                option_name="--signer",
                message=click.style(
                    "--signer must be provided to create new ritual",
                    fg="red",
                ),
            )
        if access_controller is None:
            raise click.BadOptionUsage(
                option_name="--access-controller",
                message=click.style(
                    "--access-controller must be provided to create new ritual",
                    fg="red",
                ),
            )
        if num_rituals < 1:
            raise click.BadOptionUsage(
                option_name="--num-rituals",
                message=click.style("Number of rituals must be >= 1", fg="red"),
            )

    if ritual_id >= 0:
        # if re-using existing ritual
        if access_controller:
            raise click.BadOptionUsage(
                option_name="--access-controller",
                message=click.style(
                    "--access-controller not needed since it is obtained from the Coordinator",
                    fg="red",
                ),
            )

        if num_rituals != 1:
            raise click.BadOptionUsage(
                option_name="--ritual-id, --num-rituals",
                message=click.style(
                    "--ritual-id and --num-rituals cannot be used together", fg="red"
                ),
            )
        if dkg_size != 0:
            raise click.BadOptionUsage(
                option_name="--ritual-id, --dkg-size",
                message=click.style(
                    "--ritual-id and --dkg-size cannot be used together", fg="red"
                ),
            )

    domain = domains.get_domain(domain)
    registry = ContractRegistry.from_latest_publication(domain=domain)
    coordinator_agent = ContractAgency.get_agent(
        agent_class=CoordinatorAgent,
        registry=registry,
        blockchain_endpoint=polygon_endpoint,
    )  # type: CoordinatorAgent

    child_application_agent = ContractAgency.get_agent(
        agent_class=TACoChildApplicationAgent,
        registry=registry,
        blockchain_endpoint=polygon_endpoint,
    )  # type: TACoChildApplicationAgent

    #
    # Get deployer account
    #
    signer = None
    transacting_power = None

    # Get AccessController contract
    blockchain = coordinator_agent.blockchain

    #
    # Initiate Ritual(s)
    #
    if ritual_id < 0:
        # Obtain transacting power
        signer = Signer.from_signer_uri(uri=signer_uri)
        account_address = signer.accounts[0]
        transacting_power = get_transacting_power(signer=signer)

        emitter.echo("--------- Initiating Ritual ---------", color="yellow")
        emitter.echo(
            f"Commencing DKG Ritual(s) on {domain.polygon_chain.name} using {account_address}",
            color="green",
        )

        access_controller_contract = blockchain.get_contract_by_name(
            registry=registry, contract_name=access_controller
        )

        initiated_rituals = []
        for i in range(num_rituals):
            # find staking addresses
            (
                _,
                staking_providers_dict,
            ) = child_application_agent.get_all_active_staking_providers()
            staking_providers = list(staking_providers_dict.keys())

            if domain == domains.LYNX:
                # Ignore delinquent lynx providers
                exclude_staking_providers = [
                    "0x24dbb0BEE134C3773D2C1791d65d99e307Fe86CF",
                    "0xE4c8d3bcf8C87D73CE38Ab2DC288d309072ee4E7",
                ]
                for provider in exclude_staking_providers:
                    try:
                        staking_providers.remove(provider)
                    except ValueError:
                        pass

            # sample then sort
            dkg_staking_providers = random.sample(staking_providers, dkg_size)
            dkg_staking_providers.sort()
            emitter.echo(f"Using staking providers for DKG: {dkg_staking_providers}")
            receipt = coordinator_agent.initiate_ritual(
                providers=dkg_staking_providers,
                authority=account_address,
                duration=ritual_duration,
                access_controller=access_controller_contract.address,
                transacting_power=transacting_power,
            )
            start_ritual_event = (
                coordinator_agent.contract.events.StartRitual().process_receipt(receipt)
            )
            ritual_id = start_ritual_event[0]["args"]["ritualId"]
            ritual_status = coordinator_agent.get_ritual_status(ritual_id)
            assert (
                ritual_status != Coordinator.RitualStatus.NON_INITIATED
            ), "ritual successfully initiated"

            initiated_rituals.append(ritual_id)
            emitter.echo(
                f"DKG Ritual #{ritual_id} initiated; tx: {Web3.to_hex(receipt['transactionHash'])}",
                color="green",
            )

        #
        # Wait for Ritual(s) to complete
        # TODO perhaps reuse EventActuator here
        #
        completed_rituals = dict()
        start_time = maya.now()
        while True:
            for initiated_ritual in initiated_rituals:
                if initiated_ritual in completed_rituals:
                    # already completed
                    continue

                ritual_status = coordinator_agent.get_ritual_status(initiated_ritual)
                if ritual_status == Coordinator.RitualStatus.ACTIVE:
                    # success
                    emitter.echo(
                        f"DKG Ritual #{initiated_ritual} completed after {(maya.now() - start_time).seconds}s",
                        color="green",
                    )
                    completed_rituals[initiated_ritual] = ritual_status
                elif (
                    # failure
                    ritual_status == Coordinator.RitualStatus.DKG_TIMEOUT
                    or ritual_status == Coordinator.RitualStatus.DKG_INVALID
                ):
                    emitter.error(
                        f"Ritual #{initiated_ritual} failed with status '{ritual_status}'"
                    )
                    completed_rituals[initiated_ritual] = ritual_status

            if len(completed_rituals) >= num_rituals:
                break

            emitter.echo(
                f"Waiting for Ritual(s) to complete ({len(completed_rituals)} / {num_rituals} completed); {(maya.now() - start_time).seconds}s elapsed thus far"
            )
            time.sleep(15)

        emitter.echo("\n--------- Ritual(s) Summary ---------")
        # sort by ritual id, print results, stop script
        for r_id in sorted(completed_rituals.keys()):
            ritual_status = completed_rituals[r_id]
            if ritual_status == Coordinator.RitualStatus.ACTIVE:
                message = f"✓ Ritual #{r_id} successfully created"
                color = "green"
            else:
                message = f"x Ritual #{r_id} failed with status {ritual_status}"
                color = "red"

            emitter.echo(message, color=color)
        return
    else:
        emitter.echo(f"Reusing existing DKG Ritual #{ritual_id}", color="green")

    ritual = coordinator_agent.get_ritual(ritual_id)  # ensure ritual can be found

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
            "conditionType": ConditionType.TIME.value,
            "returnValueTest": {"value": 0, "comparator": ">"},
            "method": "blocktime",
            "chain": child_application_agent.blockchain.client.chain_id,
        },
    }

    encrypting_key = DkgPublicKey.from_bytes(bytes(ritual.public_key))

    private_key = None
    if not use_random_enrico:
        # use known enrico address
        print("Using default Enrico signing account")
        private_key = DEFAULT_TEST_ENRICO_PRIVATE_KEY

    enrico_signer = InMemorySigner(private_key)
    enrico_account = enrico_signer.accounts[0]
    emitter.echo(f"Using account {enrico_account} to sign data")

    enrico = Enrico(encrypting_key=encrypting_key, signer=enrico_signer)
    threshold_message_kit = enrico.encrypt_for_dkg(
        plaintext=PLAINTEXT.encode(), conditions=CONDITIONS
    )
    emitter.echo("-- Data encrypted --", color="green")

    allow_list = blockchain.get_contract_by_name(
        registry=registry, contract_name=GLOBAL_ALLOW_LIST
    )
    if ritual.access_controller == allow_list.address:
        #
        # Authorize Enrico to use the ritual
        #
        is_enrico_already_authorized = allow_list.functions.isAddressAuthorized(
            ritual_id, enrico_account
        ).call()
        if is_enrico_already_authorized:
            emitter.echo(
                f"Enrico {enrico_account} already authorized for DKG Ritual #{ritual_id}",
                color="green",
            )
        elif click.confirm(f"Do you want to authorize Enrico ('{enrico_account}')?"):
            # Obtain transacting power
            if not signer_uri:
                emitter.echo(
                    "--signer must be provided to initiate rituals", color="red"
                )
                return click.Abort()

            if not signer:
                signer = Signer.from_signer_uri(uri=signer_uri)

            if not transacting_power:
                transacting_power = get_transacting_power(signer)

            # Authorize Enrico
            contract_function = allow_list.functions.authorize(
                ritual_id, [enrico_account]
            )
            blockchain.send_transaction(
                contract_function=contract_function, transacting_power=transacting_power
            )
            emitter.echo(
                f"Enrico {enrico_account} authorized to use DKG Ritual #{ritual_id}",
                color="green",
            )
        else:
            emitter.echo(
                f"Enrico {enrico_account} may/may not be authorized to use DKG Ritual #{ritual_id} - decryption may fail",
                color="yellow",
            )
    else:
        emitter.echo(
            f"No authorization checked/performed - Enrico {enrico_account} may/may not be authorized to use DKG Ritual #{ritual_id} - decryption may fail",
            color="yellow",
        )

    #
    # Get Data Decrypted
    #
    emitter.echo("--------- Threshold Decryption ---------")
    bob = Bob(
        domain=domain,
        eth_endpoint=eth_endpoint,
        polygon_endpoint=polygon_endpoint,
        registry=registry,
    )
    bob.start_learning_loop(now=True)

    cleartext = bob.threshold_decrypt(
        threshold_message_kit=threshold_message_kit,
    )

    emitter.echo(f"\n-- Data decrypted -- \n{bytes(cleartext).decode()}", color="green")
    assert bytes(cleartext).decode() == PLAINTEXT


if __name__ == "__main__":
    nucypher_dkg()
