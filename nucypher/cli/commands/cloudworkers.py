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

try:
    from nucypher.utilities.clouddeploy import CloudDeployers
except ImportError:
    CloudDeployers = None
from nucypher.cli.utils import setup_emitter
from nucypher.config.characters import StakeHolderConfiguration
from nucypher.cli.commands.stake import group_staker_options, option_config_file, group_general_config


def filter_staker_addresses(stakers, stakes):

    staker_addresses = set()
    for staker in stakers:

        for stake in staker.stakes:
            if stakes:
                if not stake.staker_address in stakes:
                    continue
            staker_addresses.add(stake.staker_address)
    return staker_addresses


@click.group()
def cloudworkers():
    """Manage stakes and other staker-related operations."""

@cloudworkers.command('up')
@group_staker_options
@option_config_file
@click.option('--cloudprovider', help="aws or digitalocean", default='aws')
@click.option('--aws-profile', help="The cloud provider account profile you'd like to use (an aws profile)", default=None)
@click.option('--remote-provider', help="The blockchain provider for the remote node, if not provided, nodes will run geth.", default=None)
@click.option('--nucypher-image', help="The docker image containing the nucypher code to run on the remote nodes. (default is nucypher/nucypher:latest)", default=None)
@click.option('--seed-network', help="Do you want the 1st node to be --lonely and act as a seed node for this network", default=False, is_flag=True)
@click.option('--sentry-dsn', help="a sentry dsn for these workers (https://sentry.io/)", default=None)
@click.option('--include-stakeholder', 'stakes', help="limit worker to specified stakeholder addresses", multiple=True)
@click.option('--wipe', help="Clear nucypher configs on existing nodes and start a fresh node with new keys.", default=False, is_flag=True)
@click.option('--prometheus', help="Run Prometheus on workers.", default=False, is_flag=True)
@group_general_config
def up(general_config, staker_options, config_file, cloudprovider, aws_profile, remote_provider, nucypher_image, seed_network, sentry_dsn, stakes, wipe, prometheus):
    """Creates workers for all stakes owned by the user for the given network."""

    emitter = setup_emitter(general_config)

    if not CloudDeployers:
        emitter.echo("Ansible is required to use this command.  (Please run 'pip install ansible'.)", color="red")
        return
    STAKEHOLDER = staker_options.create_character(emitter, config_file)

    stakers = STAKEHOLDER.get_stakers()
    if not stakers:
        emitter.echo("No staking accounts found.")
        return

    staker_addresses = filter_staker_addresses(stakers, stakes)

    config_file = config_file or StakeHolderConfiguration.default_filepath()

    deployer = CloudDeployers.get_deployer(cloudprovider)(emitter, STAKEHOLDER, config_file, remote_provider, nucypher_image, seed_network, sentry_dsn, aws_profile, prometheus)
    config = deployer.create_nodes_for_stakers(staker_addresses)

    if config.get('instances') and len(config.get('instances')) >= len(staker_addresses):
        emitter.echo('Nodes exist for all requested stakes', color="yellow")
        deployer.deploy_nucypher_on_existing_nodes(staker_addresses, wipe_nucypher=wipe)


@cloudworkers.command('add')
@group_staker_options
@option_config_file
@click.option('--staker-address',  help="The staker account address for whom you are adding a worker host.", required=True)
@click.option('--host-address', help="The IP address or Hostname of the host you are adding.", required=True)
@click.option('--login-name', help="The name username of a user with root privileges we can ssh as on the host.", required=True)
@click.option('--key-path', help="The path to a keypair we will need to ssh into this host", default="~/.ssh/id_rsa.pub")
@click.option('--ssh-port', help="The port this host's ssh daemon is listening on", default=22)
@group_general_config
def add(general_config, staker_options, config_file, staker_address, host_address, login_name, key_path, ssh_port):
    """Creates workers for all stakes owned by the user for the given network."""

    emitter = setup_emitter(general_config)

    STAKEHOLDER = staker_options.create_character(emitter, config_file)

    stakers = STAKEHOLDER.get_stakers()
    if not stakers:
        emitter.echo("No staking accounts found.")
        return

    staker_addresses = filter_staker_addresses(stakers, [staker_address])
    if not staker_addresses:
        emitter.echo(f"Could not find staker address: {staker_address} among your stakes. (try `nucypher stake --list`)", color="red")
        return

    config_file = config_file or StakeHolderConfiguration.default_filepath()

    deployer = CloudDeployers.get_deployer('generic')(emitter, STAKEHOLDER, config_file)
    config = deployer.create_nodes_for_stakers(staker_addresses, host_address, login_name, key_path, ssh_port)



@cloudworkers.command('deploy')
@group_staker_options
@option_config_file
@click.option('--remote-provider', help="The blockchain provider for the remote node, if not provided nodes will run geth.", default=None)
@click.option('--nucypher-image', help="The docker image containing the nucypher code to run on the remote nodes.", default=None)
@click.option('--seed-network', help="Do you want the 1st node to be --lonely and act as a seed node for this network", default=False, is_flag=True)
@click.option('--sentry-dsn', help="a sentry dsn for these workers (https://sentry.io/)", default=None)
@click.option('--include-stakeholder', 'stakes', help="limit worker to specified stakeholder addresses", multiple=True)
@click.option('--wipe', help="Clear your nucypher config and start a fresh node with new kets", default=False, is_flag=True)
@click.option('--prometheus', help="Run Prometheus on workers.", default=False, is_flag=True)
@group_general_config
def deploy(general_config, staker_options, config_file, remote_provider, nucypher_image, seed_network, sentry_dsn, stakes, wipe, prometheus):
    """Deploys NuCypher on existing hardware."""

    emitter = setup_emitter(general_config)

    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return
    STAKEHOLDER = staker_options.create_character(emitter, config_file)

    stakers = STAKEHOLDER.get_stakers()
    if not stakers:
        emitter.echo("No staking accounts found.")
        return

    staker_addresses = filter_staker_addresses(stakers, stakes)

    config_file = config_file or StakeHolderConfiguration.default_filepath()

    deployer = CloudDeployers.get_deployer('generic')(emitter, STAKEHOLDER, config_file, remote_provider, nucypher_image, seed_network, sentry_dsn, prometheus=prometheus)

    emitter.echo("found nodes for the following stakers:")
    for staker_address in staker_addresses:
        if deployer.config['instances'].get(staker_address):
            data = deployer.config['instances'].get(staker_address)
            emitter.echo(f'\t{staker_address}: {data["publicaddress"]}', color="yellow")
    deployer.deploy_nucypher_on_existing_nodes(staker_addresses, wipe_nucypher=wipe)


@cloudworkers.command('destroy')
@group_staker_options
@option_config_file
@click.option('--cloudprovider', help="aws or digitalocean")
@click.option('--include-stakeholder', 'stakes', help="one or more stakeholder addresses to whom we should limit worker destruction", multiple=True)
@group_general_config
def destroy(general_config, staker_options, config_file, cloudprovider, stakes):
    """Cleans up all previously created resources for the given netork for the cloud providern"""

    emitter = setup_emitter(general_config)
    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return
    STAKEHOLDER = staker_options.create_character(emitter, config_file)

    stakers = STAKEHOLDER.get_stakers()
    if not stakers:
        emitter.echo("No staking accounts found.")
        return

    staker_addresses = filter_staker_addresses(stakers, stakes)

    config_file = config_file or StakeHolderConfiguration.default_filepath()
    deployer = CloudDeployers.get_deployer(cloudprovider)(emitter, STAKEHOLDER, config_file)
    deployer.destroy_resources(staker_addresses=staker_addresses)


@cloudworkers.command('status')
@group_staker_options
@option_config_file
@click.option('--cloudprovider', help="aws or digitalocean", default='aws')
@click.option('--include-stakeholder', 'stakes', help="only show nodes for included stakeholder addresses", multiple=True)
@group_general_config
def status(general_config, staker_options, config_file, cloudprovider, stakes):
    """Displays worker status and updates worker data in stakeholder config"""

    emitter = setup_emitter(general_config)
    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return
    STAKEHOLDER = staker_options.create_character(emitter, config_file)
    config_file = config_file or StakeHolderConfiguration.default_filepath()
    deployer = CloudDeployers.get_deployer(cloudprovider)(emitter, STAKEHOLDER, config_file)

    stakers = STAKEHOLDER.get_stakers()
    staker_addresses = filter_staker_addresses(stakers, stakes)

    deployer.get_worker_status(staker_addresses)
