# Run nucypher dkg by running:
#
#    python scripts/hooks/nucypher_dkg.py <ETH_PROVIDER_URI> <RITUAL_ID> <NETWORK> <SIGNER_URI>
#
# For example:
#
# Use existing ritual id (eg. id '0'):
#    python ./scripts/hooks/nucypher_dkg.py <ETH_PROVIDER_URI> 0 lynx
#
# Go through entire process of initiating a ritual, waiting for it to finish, then use for encryption/decryption:
#    python ./scripts/hooks/nucypher_dkg.py <ETH_PROVIDER_URI> -1 lynx <SIGNER_URI>
#

import random
import sys
import time

import click
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION
from ferveo_py import DkgPublicKey
from web3 import Web3

from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    PREApplicationAgent,
)
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import (
    BaseContractRegistry,
    GithubRegistrySource,
    InMemoryContractRegistry,
    RegistrySourceManager,
)
from nucypher.blockchain.eth.signers import Signer
from nucypher.characters.lawful import Bob, Enrico, Ursula
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.logging import GlobalLoggerSettings

NO_BLOCKCHAIN_CONNECTION.bool_value(False)  # FIXME

GlobalLoggerSettings.start_console_logging()

emitter = StdoutEmitter(verbosity=2)


class TDecGithubRegistrySource(GithubRegistrySource):
    def get_publication_endpoint(self) -> str:
        url = f"{self._BASE_URL}/tdec/nucypher/blockchain/eth/contract_registry/{self.network}/{self.registry_name}"
        return url


try:
    eth_provider_uri = sys.argv[1]
except IndexError:
    emitter.message("You have to pass a provider URI", color="red")
    sys.exit(-1)

try:
    ritual_id = int(sys.argv[2])
    if ritual_id == -1:
        ritual_id = None
except IndexError:
    ritual_id = None

try:
    signer_uri = sys.argv[4]
except IndexError:
    if ritual_id is None:
        emitter.message(
            "You must provide an account signer URI for new ritual transactions if not reusing a ritual id",
            color="red",
        )
        sys.exit(-1)
    signer_uri = None

try:
    network = sys.argv[3]
except IndexError:
    network = "lynx"


BlockchainInterfaceFactory.initialize_interface(
    eth_provider_uri=eth_provider_uri, light=False, emitter=emitter
)
blockchain = BlockchainInterfaceFactory.get_interface(eth_provider_uri=eth_provider_uri)

emitter.echo(message="Reading Latest Chaindata...")
blockchain.connect()

github_source = TDecGithubRegistrySource(
    network=network, registry_name=BaseContractRegistry.REGISTRY_NAME
)
source_manager = RegistrySourceManager(sources=[github_source])
registry = InMemoryContractRegistry.from_latest_publication(
    source_manager=source_manager, network=network
)
emitter.echo(f"NOTICE: Connecting to {network} network", color="yellow")

application_agent = ContractAgency.get_agent(
    agent_class=PREApplicationAgent, registry=registry
)  # type: PREApplicationAgent
coordinator_agent = ContractAgency.get_agent(
    agent_class=CoordinatorAgent, registry=registry
)  # type: CoordinatorAgent

#
# Initial Ritual
#
# must be a power of 2
if ritual_id is None:
    emitter.echo("--------- Initiating Ritual ---------")
    # create account from keystore file
    signer = Signer.from_signer_uri(uri=signer_uri)
    account_address = signer.accounts[0]
    emitter.echo(f"Using account {account_address}", color="green")

    password = click.prompt(
        "Enter your keystore password", confirmation_prompt=False, hide_input=True
    )
    signer.unlock_account(account=account_address, password=password)
    transacting_power = TransactingPower(signer=signer, account=account_address)

    emitter.echo(
        f"Ready to commence DKG Ritual on {network} using {account_address}",
        color="green",
    )

    # find staking addresses
    _, staking_providers_dict = application_agent.get_all_active_staking_providers()
    staking_providers = list(staking_providers_dict.keys())
    staking_providers.remove(
        "0x7AFDa7e47055CDc597872CA34f9FE75bD083D0Fe"
    )  # TODO why is this address active? It doesn't have a running node

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
        f"DKG Ritual {ritual_id} initiated: {Web3.to_hex(receipt['transactionHash'])}",
        color="green",
    )

    #
    # Wait for Ritual to complete
    # TODO perhaps reuse EventActuator here
    #
    start_time = time.time()
    while True:
        ritual_status = coordinator_agent.get_ritual_status(ritual_id)

        if ritual_status == coordinator_agent.Ritual.Status.FINALIZED:
            break

        if (
            ritual_status == coordinator_agent.Ritual.Status.TIMEOUT
            or ritual_status == coordinator_agent.Ritual.Status.INVALID
        ):
            emitter.error(f"Ritual {ritual_id} failed with status {ritual_status}")
            sys.exit(-1)

        emitter.echo(
            f"Waiting for Ritual to complete; {time.time() - start_time}s elapsed thus far"
        )
        time.sleep(10)

    emitter.echo(
        f"DKG Ritual ended with status {ritual_status} after {time.time() - start_time}s"
    )
else:
    ritual = coordinator_agent.get_ritual(ritual_id)  # ensure ritual can be found
    emitter.echo(f"Reusing existing DKG Ritual {ritual_id}", color="green")

#
# Encrypt some data
#
emitter.echo("--------- Data Encryption ---------")

PLAINTEXT = """
Those who mistake the unessential to be essential and the essential to be unessential, dwelling in wrong thoughts, never arrive at the essential.
Those who know the essential to be essential and the unessential to be unessential, dwelling in right thoughts, do arrive at the essential.
"""
# -- Dhammapada

CONDITIONS = [
    {"returnValueTest": {"value": "0", "comparator": ">"}, "method": "timelock"}
]
encrypting_key = DkgPublicKey.from_bytes(
    coordinator_agent.get_ritual(ritual_id).public_key
)

enrico = Enrico(encrypting_key=encrypting_key)
ciphertext = enrico.encrypt_for_dkg(plaintext=PLAINTEXT.encode(), conditions=CONDITIONS)

emitter.echo("Data encrypted", color="green")

#
# Get Data Decrypted
#
emitter.echo("--------- Threshold Decryption ---------")
bob = Bob(
    eth_provider_uri=eth_provider_uri,
    domain=network,
    registry=registry,
    known_nodes=[
        Ursula.from_teacher_uri(f"https://{network}.nucypher.network:9151", min_stake=0)
    ],
)
bob.start_learning_loop(now=True)

cleartext = bob.threshold_decrypt(
    ritual_id=ritual_id,
    ciphertext=ciphertext,
    conditions=CONDITIONS,
    # uncomment to use the precomputed variant
    # variant=FerveoVariant.PRECOMPUTED.name
)

emitter.echo(f"Data decrypted: \n{bytes(cleartext).decode()}", color="green")
assert bytes(cleartext).decode() == PLAINTEXT
