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


import click
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION
from twisted.internet import stdio

from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.characters.banners import URSULA_BANNER
from nucypher.cli import actions, painting
from nucypher.cli.actions import (
    get_nucypher_password,
    select_client_account,
    get_client_password
)
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.processes import UrsulaCommandProtocol
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    NETWORK_PORT,
    EXISTING_READABLE_FILE
)
from nucypher.config.characters import UrsulaConfiguration
from nucypher.utilities.sandbox.constants import (
    TEMPORARY_DOMAIN,
)


@click.command()
@click.argument('action')
@click.option('--dev', '-d', help="Enable development mode", is_flag=True)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True, default=None)
@click.option('--lonely', help="Do not connect to seednodes", is_flag=True)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--teacher', 'teacher_uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--rest-host', help="The host IP address to run Ursula network services on", type=click.STRING)
@click.option('--rest-port', help="The host port to run Ursula network services on", type=NETWORK_PORT)
@click.option('--db-filepath', help="The database filepath to connect to", type=click.STRING)
@click.option('--staker-address', help="Run on behalf of a specified staking account", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--worker-address', help="Run the worker-ursula with a specified address", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True, default=None)
@click.option('--interactive', '-I', help="Launch command interface after connecting to seednodes.", is_flag=True, default=False)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=None)
@click.option('--geth', '-G', help="Run using the built-in geth node", is_flag=True)
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@nucypher_click_config
def ursula(click_config,
           action,
           dev,
           dry_run,
           force,
           lonely,
           network,
           teacher_uri,
           min_stake,
           rest_host,
           rest_port,
           db_filepath,
           staker_address,
           worker_address,
           federated_only,
           poa,
           config_root,
           config_file,
           provider_uri,
           geth,
           registry_filepath,
           interactive,
           ) -> None:
    """
    "Ursula the Untrusted" PRE Re-encryption node management commands.

    \b
    Actions
    -------------------------------------------------
    \b
    init              Create a new Ursula node configuration.
    view              View the Ursula node's configuration.
    run               Run an "Ursula" node.
    save-metadata     Manually write node metadata to disk without running
    forget            Forget all known nodes.
    destroy           Delete Ursula node configuration.
    confirm-activity  Manually confirm-activity for the current period.

    """

    emitter = click_config.emitter

    #
    # Validate
    #

    if federated_only:
        if geth:
            raise click.BadOptionUsage(option_name="--geth",
                                       message="Federated only cannot be used with the --geth flag")

        if staker_address:
            raise click.BadOptionUsage(option_name='--federated-only',
                                       message="Staking address cannot be used in federated mode.")

    # Banner
    emitter.banner(URSULA_BANNER.format(worker_address or ''))

    #
    # Pre-Launch Warnings
    #

    if dev:
        emitter.echo("WARNING: Running in Development mode", color='yellow', verbosity=1)
    if force:
        emitter.echo("WARNING: Force is enabled", color='yellow', verbosity=1)

    #
    # Internal Ethereum Client
    #

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    if geth:
        ETH_NODE = actions.get_provider_process()
        provider_uri = ETH_NODE.provider_uri(scheme='file')


    #
    # Eager Actions
    #

    if action == "init":
        """Create a brand-new persistent Ursula"""

        if dev:
            raise click.BadArgumentUsage("Cannot create a persistent development character")

        if (not staker_address or not worker_address) and not federated_only:

            # Connect to Blockchain
            registry = None
            if registry_filepath:
                registry = EthereumContractRegistry(registry_filepath=registry_filepath)
            blockchain = BlockchainInterface(provider_uri=provider_uri, registry=registry, poa=poa)
            blockchain.connect(fetch_registry=False)

            if not staker_address:
                prompt = "Select staker account"
                staker_address = select_client_account(emitter=emitter, blockchain=blockchain, prompt=prompt)

            if not worker_address:
                prompt = "Select worker account"
                worker_address = select_client_account(emitter=emitter, blockchain=blockchain, prompt=prompt)

        if not config_root:                         # Flag
            config_root = click_config.config_file  # Envvar

        if not rest_host:
            rest_host = actions.determine_external_ip_address(emitter, force=force)

        ursula_config = UrsulaConfiguration.generate(password=get_nucypher_password(confirm=True),
                                                     config_root=config_root,
                                                     rest_host=rest_host,
                                                     rest_port=rest_port,
                                                     db_filepath=db_filepath,
                                                     domains={network} if network else None,
                                                     federated_only=federated_only,
                                                     checksum_address=staker_address,
                                                     worker_address=worker_address,
                                                     download_registry=federated_only or click_config.no_registry,
                                                     registry_filepath=registry_filepath,
                                                     provider_process=ETH_NODE,
                                                     provider_uri=provider_uri,
                                                     poa=poa)

        painting.paint_new_installation_help(emitter, new_configuration=ursula_config)
        return

    #
    # Make Ursula
    #

    if dev:
        ursula_config = UrsulaConfiguration(dev_mode=True,
                                            domains={TEMPORARY_DOMAIN},
                                            poa=poa,
                                            download_registry=False,
                                            registry_filepath=registry_filepath,
                                            provider_process=ETH_NODE,
                                            provider_uri=provider_uri,
                                            checksum_address=staker_address,
                                            worker_address=worker_address,
                                            federated_only=federated_only,
                                            rest_host=rest_host,
                                            rest_port=rest_port,
                                            db_filepath=db_filepath)
    else:
        try:
            ursula_config = UrsulaConfiguration.from_configuration_file(filepath=config_file,
                                                                        domains={network} if network else None,
                                                                        registry_filepath=registry_filepath,
                                                                        provider_process=ETH_NODE,
                                                                        provider_uri=provider_uri,
                                                                        rest_host=rest_host,
                                                                        rest_port=rest_port,
                                                                        db_filepath=db_filepath,
                                                                        poa=poa,
                                                                        federated_only=federated_only)
        except FileNotFoundError:
            return actions.handle_missing_configuration_file(character_config_class=UrsulaConfiguration,
                                                             config_file=config_file)
        except Exception as e:
            if click_config.debug:
                raise
            else:
                emitter.echo(str(e), color='red', bold=True)
                raise click.Abort

    #
    # Configured Pre-Authentication Actions
    #

    # Handle destruction *before* network bootstrap and character initialization below
    if action == "destroy":
        """Delete all configuration files from the disk"""
        if dev:
            message = "'nucypher ursula destroy' cannot be used in --dev mode - There is nothing to destroy."
            raise click.BadOptionUsage(option_name='--dev', message=message)
        return actions.destroy_configuration(emitter, character_config=ursula_config, force=force)

    #
    # Make Ursula
    #
    # TODO: OH MY INDEED
    client_password = None
    if not ursula_config.federated_only:
        if not dev and not click_config.json_ipc:
            client_password = get_client_password(checksum_address=ursula_config.worker_address)
    URSULA = actions.make_cli_character(character_config=ursula_config,
                                        click_config=click_config,
                                        min_stake=min_stake,
                                        teacher_uri=teacher_uri,
                                        dev=dev,
                                        lonely=lonely,
                                        client_password=client_password)

    #
    # Authenticated Action Switch
    #

    if action == 'run':
        """Seed, Produce, Run!"""

        # GO!
        try:

            # Ursula Deploy Warnings
            emitter.message(
                f"Starting Ursula on {URSULA.rest_interface}",
                color='green',
                bold=True)

            emitter.message(
                f"Connecting to {','.join(ursula_config.domains)}",
                color='green',
                bold=True)

            emitter.message(
                "Working ~ Keep Ursula Online!",
                color='blue',
                bold=True)

            if interactive:
                stdio.StandardIO(UrsulaCommandProtocol(ursula=URSULA, emitter=emitter))

            if dry_run:
                return  # <-- ABORT - (Last Chance)

            # Run - Step 3
            node_deployer = URSULA.get_deployer()
            node_deployer.addServices()
            node_deployer.catalogServers(node_deployer.hendrix)
            node_deployer.run()   # <--- Blocking Call (Reactor)

        # Handle Crash
        except Exception as e:
            ursula_config.log.critical(str(e))
            emitter.message(
                f"{e.__class__.__name__} {e}",
                color='red',
                bold=True)
            raise  # Crash :-(

        # Graceful Exit
        finally:
            emitter.message("Stopping Ursula", color='green')
            ursula_config.cleanup()
            emitter.message("Ursula Stopped", color='red')
        return

    elif action == "save-metadata":
        """Manually save a node self-metadata file"""
        metadata_path = ursula.write_node_metadata(node=URSULA)
        emitter.message(f"Successfully saved node metadata to {metadata_path}.", color='green')
        return

    elif action == "view":
        """Paint an existing configuration to the console"""

        if not URSULA.federated_only:
            emitter.echo("BLOCKCHAIN ----------\n")
            painting.paint_contract_status(emitter, ursula_config=ursula_config)
            current_block = URSULA.blockchain.w3.eth.blockNumber
            emitter.echo(f'Block # {current_block}')
            emitter.echo(f'NU Balance: {URSULA.token_balance}')
            emitter.echo(f'ETH Balance: {URSULA.eth_balance}')
            emitter.echo(f'Current Gas Price {URSULA.blockchain.client.gasPrice}')

        emitter.echo("CONFIGURATION --------")
        response = UrsulaConfiguration._read_configuration_file(filepath=config_file or ursula_config.config_file_location)
        return emitter.ipc(response=response, request_id=0, duration=0) # FIXME: what are request_id and duration here?

    elif action == "forget":
        actions.forget(emitter, configuration=ursula_config)
        return

    elif action == 'confirm-activity':
        receipt = URSULA.confirm_activity()

        confirmed_period = URSULA.staking_agent.get_current_period() + 1
        txhash = receipt["transactionHash"].hex()
        date = datetime_at_period(period=confirmed_period)

        emitter.echo(f'\nActivity confirmed for period #{confirmed_period} '
                     f'(starting at {date})', bold=True, color='blue')
        emitter.echo(f'Receipt: {txhash}')
        return

    else:
        raise click.BadArgumentUsage("No such argument {}".format(action))
