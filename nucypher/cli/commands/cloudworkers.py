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
import os

try:
    from nucypher.utilities.clouddeploy import CloudDeployers
except ImportError:
    # FIXME:  Do something more meaningful and conventional here.
    # Locally scope the import instead or raising an
    # exception similar to DevelopmentInstallationRequired.
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
@click.option('--seed-network', help="Do you want the 1st node to be --lonely and act as a seed node for this network", default=None, is_flag=True)
@click.option('--include-stakeholder', 'stakes', help="limit worker to specified stakeholder addresses", multiple=True)
@click.option('--wipe', help="Clear nucypher configs on existing nodes and start a fresh node with new keys.", default=False, is_flag=True)
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING, default='local-stakeholders')
@click.option('--env', '-e', 'envvars', help="environment variables (ENVVAR=VALUE)", multiple=True, type=click.STRING, default=[])
@click.option('--cli', '-c', 'cliargs', help="cli arguments for 'nucypher run': eg.'--max-gas-price 50'/'--c max-gas-price=50'", multiple=True, type=click.STRING, default=[])
@group_general_config
def up(general_config, staker_options, config_file, cloudprovider, aws_profile, remote_provider, nucypher_image, seed_network, stakes, wipe, namespace, envvars, cliargs):
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

    deployer = CloudDeployers.get_deployer(cloudprovider)(emitter, STAKEHOLDER, config_file, remote_provider,
        nucypher_image, seed_network, aws_profile, namespace=namespace, network=STAKEHOLDER.network, envvars=envvars, cliargs=cliargs)
    if staker_addresses:
        config = deployer.create_nodes(staker_addresses)

    if config.get('instances') and len(config.get('instances')) >= len(staker_addresses):
        emitter.echo('Nodes exist for all requested stakes', color="yellow")
        deployer.deploy_nucypher_on_existing_nodes(staker_addresses, wipe_nucypher=wipe)


@cloudworkers.command('create')
@click.option('--cloudprovider', help="aws or digitalocean", default='aws')
@click.option('--aws-profile', help="The AWS account profile you'd like to use (option not required for DigitalOcean users)", default=None)
@click.option('--remote-provider', help="The blockchain provider for the remote node, if not provided, nodes will run geth.", default=None)
@click.option('--nucypher-image', help="The docker image containing the nucypher code to run on the remote nodes. (default is nucypher/nucypher:latest)", default=None)
@click.option('--seed-network', help="Do you want the 1st node to be --lonely and act as a seed node for this network", default=None, is_flag=True)
@click.option('--count', help="Create this many nodes.", type=click.INT, default=1)
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING, default='local-stakeholders')
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@click.option('--env', '-e', 'envvars', help="environment variables (ENVVAR=VALUE)", multiple=True, type=click.STRING, default=[])
@click.option('--cli', '-c', 'cliargs', help="cli arguments for 'nucypher run': eg.'--max-gas-price 50'/'--c max-gas-price=50'", multiple=True, type=click.STRING, default=[])
@group_general_config
def create(general_config, cloudprovider, aws_profile, remote_provider, nucypher_image, seed_network, count, namespace, network, envvars, cliargs):
    """Creates the required number of workers to be staked later under a namespace"""

    emitter = setup_emitter(general_config)

    if not CloudDeployers:
        emitter.echo("Ansible is required to use this command.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer(cloudprovider)(emitter, None, None, remote_provider, nucypher_image, seed_network,
        profile=aws_profile, namespace=namespace, network=network, envvars=envvars, cliargs=cliargs)

    names = []
    i = 1
    while len(names) < count:
        name = f'{namespace}-{network}-{i}'
        if name not in deployer.config.get('instances', {}):
            names.append(name)
        i += 1
    config = deployer.create_nodes(names, unstaked=True)

    if config.get('instances') and len(config.get('instances')) >= count:
        emitter.echo('The requested number of nodes now exist', color="green")
        deployer.deploy_nucypher_on_existing_nodes(names)


@cloudworkers.command('add')
@click.option('--host-address', help="The IP address or Hostname of the host you are adding.", required=True)
@click.option('--login-name', help="The name username of a user with root privileges we can ssh as on the host.", required=True)
@click.option('--key-path', help="The path to a keypair we will need to ssh into this host", default="~/.ssh/id_rsa")
@click.option('--ssh-port', help="The port this host's ssh daemon is listening on", default=22)
@click.option('--host-nickname', help="A nickname to remember this host by", type=click.STRING, required=True)
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING, required=True, default='local-stakeholders')
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@group_general_config
def add(general_config, host_address, login_name, key_path, ssh_port, host_nickname, namespace, network):
    """Adds an existing node to the local config for future management."""

    emitter = setup_emitter(general_config)
    name = host_nickname

    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(emitter, None, None, namespace=namespace, network=network, action='add')
    config = deployer.create_nodes([name], host_address, login_name, key_path, ssh_port)
    emitter.echo(f'Success.  Now run `nucypher cloudworkers deploy --namespace {namespace} --remote-provider <an eth provider>` to deploy Nucypher on this node.', color='green')


@cloudworkers.command('add_for_stake')
@group_staker_options
@option_config_file
@click.option('--staker-address',  help="The staker account address for whom you are adding a worker host.", required=True)
@click.option('--host-address', help="The IP address or Hostname of the host you are adding.", required=True)
@click.option('--login-name', help="The name username of a user with root privileges we can ssh as on the host.", required=True)
@click.option('--key-path', help="The path to a keypair we will need to ssh into this host", default="~/.ssh/id_rsa.pub")
@click.option('--ssh-port', help="The port this host's ssh daemon is listening on", default=22)
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING, default='local-stakeholders')
@group_general_config
def add_for_stake(general_config, staker_options, config_file, staker_address, host_address, login_name, key_path, ssh_port, namespace):
    """Sets an existing node as the host for the given staker address."""

    emitter = setup_emitter(general_config)

    STAKEHOLDER = staker_options.create_character(emitter, config_file)  # FIXME: NameErrors for 'staker options' and 'config_file'

    stakers = STAKEHOLDER.get_stakers()
    if not stakers:
        emitter.echo("No staking accounts found.")
        return

    staker_addresses = filter_staker_addresses(stakers, [staker_address])
    if not staker_addresses:
        emitter.echo(f"Could not find staker address: {staker_address} among your stakes. (try `nucypher stake --list`)", color="red")
        return

    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    config_file = config_file or StakeHolderConfiguration.default_filepath()

    deployer = CloudDeployers.get_deployer('generic')(emitter, STAKEHOLDER, config_file, namespace=namespace, network=STAKEHOLDER.network, action='add_for_stake')
    config = deployer.create_nodes(staker_addresses, host_address, login_name, key_path, ssh_port)



@cloudworkers.command('deploy')
@click.option('--remote-provider', help="The blockchain provider for the remote node, if not provided nodes will run geth.", default=None)
@click.option('--nucypher-image', help="The docker image containing the nucypher code to run on the remote nodes.", default=None)
@click.option('--seed-network', help="Do you want the 1st node to be --lonely and act as a seed node for this network", default=None, is_flag=True)
@click.option('--wipe', help="Clear your nucypher config and start a fresh node with new keys", default=False, is_flag=True)
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING, default='local-stakeholders')
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@click.option('--include-host', 'include_hosts', help="specify hosts to update", multiple=True, type=click.STRING)
@click.option('--env', '-e', 'envvars', help="environment variables (ENVVAR=VALUE)", multiple=True, type=click.STRING, default=[])
@click.option('--cli', '-c', 'cliargs', help="cli arguments for 'nucypher run': eg.'--max-gas-price 50'/'--c max-gas-price=50'", multiple=True, type=click.STRING, default=[])
@group_general_config
def deploy(general_config, remote_provider, nucypher_image, seed_network, wipe,
           namespace, network, include_hosts, envvars, cliargs):
    """Deploys NuCypher on managed hosts."""

    emitter = setup_emitter(general_config)

    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(emitter,
                                                      None,  # TODO:  Why 'None' here?  (overtly implicit)
                                                      None,  # TODO: Convert to kwargs usage for maintainability.
                                                      remote_provider,
                                                      nucypher_image,
                                                      seed_network,
                                                      namespace=namespace,
                                                      network=network,
                                                      envvars=envvars,
                                                      cliargs=cliargs)

    hostnames = deployer.config['instances'].keys()
    if include_hosts:
        hostnames = include_hosts
    for name, hostdata in [(n, d) for n, d in deployer.config['instances'].items() if n in hostnames]:
        emitter.echo(f'\t{name}: {hostdata["publicaddress"]}', color="yellow")
    deployer.deploy_nucypher_on_existing_nodes(hostnames, wipe_nucypher=wipe)


@cloudworkers.command('update')
@click.option('--remote-provider', help="The blockchain provider for the remote node – e.g. an Infura endpoint address. If not provided nodes will run geth.", default=None)
@click.option('--nucypher-image', help="The docker image containing the nucypher code to run on the remote nodes.", default=None)
@click.option('--seed-network', help="Do you want the 1st node to be --lonely and act as a seed node for this network", default=None, is_flag=True)
@click.option('--wipe', help="Clear your nucypher config and start a fresh node with new keys", default=False, is_flag=True)
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING, default='local-stakeholders')
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@click.option('--include-host', 'include_hosts', help="specify hosts to update", multiple=True, type=click.STRING)
@click.option('--env', '-e', 'envvars', help="environment variables (ENVVAR=VALUE)", multiple=True, type=click.STRING, default=[])
@click.option('--cli', '-c', 'cliargs', help="cli arguments for 'nucypher run': eg.'--max-gas-price 50'/'--c max-gas-price=50'", multiple=True, type=click.STRING, default=[])
@group_general_config
def update(general_config, remote_provider, nucypher_image, seed_network, wipe,
           namespace, network, include_hosts, envvars, cliargs):
    """Updates existing installations of Nucypher on existing managed remote hosts."""

    emitter = setup_emitter(general_config)

    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(
        emitter,
        None,
        None,
        remote_provider,
        nucypher_image,
        seed_network,
        namespace=namespace,
        network=network,
        envvars=envvars,
        cliargs=cliargs,
    )

    emitter.echo(f"updating the following existing hosts:")

    hostnames = deployer.config['instances'].keys()
    if include_hosts:
        hostnames = include_hosts
    for name, hostdata in [(n, d) for n, d in deployer.config['instances'].items() if n in hostnames]:
        emitter.echo(f'\t{name}: {hostdata["publicaddress"]}', color="yellow")
    deployer.update_nucypher_on_existing_nodes(hostnames)


@cloudworkers.command('status')
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING, default='local-stakeholders')
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@click.option('--include-host', 'include_hosts', help="Query status on only the named hosts", multiple=True, type=click.STRING)
@group_general_config
def status(general_config, namespace, network, include_hosts):
    """Displays worker status and updates worker data in stakeholder config"""

    emitter = setup_emitter(general_config)
    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(emitter, None, None, namespace=namespace, network=network)

    hostnames = deployer.config['instances'].keys()
    if include_hosts:
        hostnames = include_hosts

    deployer.get_worker_status(hostnames)


@cloudworkers.command('logs')
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING, default='local-stakeholders')
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@click.option('--include-host', 'include_hosts', help="Query status on only the named hosts", multiple=True, type=click.STRING)
@group_general_config
def logs(general_config, namespace, network, include_hosts):
    """Displays worker status and updates worker data in stakeholder config"""

    emitter = setup_emitter(general_config)
    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(emitter, None, None, namespace=namespace, network=network)

    hostnames = deployer.config['instances'].keys()
    if include_hosts:
        hostnames = include_hosts
    deployer.print_worker_logs(hostnames)


@cloudworkers.command('backup')
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING, default='local-stakeholders')
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@click.option('--include-host', 'include_hosts', help="backup only the named hosts", multiple=True, type=click.STRING)
@group_general_config
def backup(general_config, namespace, network, include_hosts):
    """Creates backups of important data from selected remote workers"""

    emitter = setup_emitter(general_config)
    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(emitter, None, None, namespace=namespace, network=network)

    hostnames = deployer.config['instances'].keys()
    if include_hosts:
        hostnames = include_hosts
    deployer.backup_remote_data(hostnames)


@cloudworkers.command('stop')
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING, default='local-stakeholders')
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@click.option('--include-host', 'include_hosts', help="stop only the named hosts", multiple=True, type=click.STRING)
@group_general_config
def stop(general_config, namespace, network, include_hosts):
    """Stops the Ursula on selected remote workers"""

    emitter = setup_emitter(general_config)
    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(emitter, None, None, namespace=namespace, network=network)

    hostnames = deployer.config['instances'].keys()
    if include_hosts:
        hostnames = include_hosts
    deployer.stop_worker_process(hostnames)


@cloudworkers.command('destroy')
@click.option('--cloudprovider', help="aws or digitalocean")
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING, default='local-stakeholders')
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@click.option('--include-host', 'include_hosts', help="Query status on only the named hosts", multiple=True, type=click.STRING)
@group_general_config
def destroy(general_config, cloudprovider, namespace, network, include_hosts):
    """Cleans up all previously created resources for the given netork for the cloud providern"""

    emitter = setup_emitter(general_config)
    if not CloudDeployers:
        emitter.echo("Ansible is required to use many `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    if not cloudprovider:
        hosts = CloudDeployers.get_deployer('generic')(emitter, None, None, network=network, namespace=namespace).get_all_hosts()
        if len(set(host['provider'] for address, host in hosts)) == 1: # check if there are hosts in this namespace
            cloudprovider = hosts[0][1]['provider']
        else:
            emitter.echo("Found hosts from multiple cloudproviders.")
            emitter.echo("We can only destroy hosts from one cloudprovider at a time.")
            emitter.echo("Please specify which provider's hosts you'd like to destroy using --cloudprovider (digitalocean or aws)")
            return
    deployer = CloudDeployers.get_deployer(cloudprovider)(emitter, None, None, network=network, namespace=namespace)

    hostnames = [name for name, data in deployer.get_provider_hosts()]
    if include_hosts:
        hostnames = include_hosts

    deployer.destroy_resources(hostnames)



@cloudworkers.command('list-namespaces')
@click.option('--network', help="The network whose namespaces you want to see.", type=click.STRING, default='mainnet')
@group_general_config
def list_namespaces(general_config, network):
    """Displays worker status and updates worker data in stakeholder config"""

    emitter = setup_emitter(general_config)
    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(emitter, None, None, network=network, pre_config={"namespace": None})
    for ns in os.listdir(deployer.network_config_path):
        emitter.echo(ns)


@cloudworkers.command('list-hosts')
@click.option('--network', help="The network whose hosts you want to see.", type=click.STRING, default='mainnet')
@click.option('--namespace', help="The network whose hosts you want to see.", type=click.STRING, default='local-stakeholders')
@group_general_config
def list_hosts(general_config, network, namespace):
    """Prints local config info about known hosts"""

    emitter = setup_emitter(general_config)
    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(emitter, None, None, network=network, namespace=namespace)
    for name, data in deployer.get_all_hosts():
        emitter.echo(name)
        if general_config.verbosity >= 2:
            for k, v in data.items():
                emitter.echo(f"\t{k}: {v}")


@cloudworkers.command('restore')
@click.option('--namespace', help="Namespace for these operations.  Used to address hosts and data locally and name hosts on cloud platforms.", type=click.STRING, default='local-stakeholders')
@click.option('--network', help="The Nucypher network name these hosts will run on.", type=click.STRING, default='mainnet')
@click.option('--target-host', 'target_host', help="The nickname managed host where we are putting the restored state.", multiple=False, type=click.STRING)
@click.option('--source-path', 'source_path', help="The absolute path to the backup data you are restoring", type=click.STRING, required=True)
@group_general_config
def restore(general_config, namespace, network, target_host, source_path):
    """Restores a backup of a worker to a running host"""

    emitter = setup_emitter(general_config)
    if not CloudDeployers:
        emitter.echo("Ansible is required to use `nucypher cloudworkers *` commands.  (Please run 'pip install ansible'.)", color="red")
        return

    deployer = CloudDeployers.get_deployer('generic')(emitter, None, None, namespace=namespace, network=network)

    deployer.restore_from_backup(target_host, source_path)
