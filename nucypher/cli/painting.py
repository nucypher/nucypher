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
import os
from decimal import Decimal

import click
import maya
from constant_sorrow.constants import NO_KNOWN_NODES

from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.characters.banners import NUCYPHER_BANNER
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.config.constants import SEEDNODES

emitter = StdoutEmitter()


def echo_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(NUCYPHER_BANNER, bold=True)
    ctx.exit()


def paint_new_installation_help(new_configuration, federated_only: bool = False, config_root=None, config_file=None):
    character_config_class = new_configuration.__class__
    character_name = character_config_class._NAME.lower()

    emitter(message="Generated keyring {}".format(new_configuration.keyring_dir), color='green')
    emitter(message="Saved configuration file {}".format(new_configuration.config_file_location), color='green')

    # Felix
    if character_name == 'felix':
        suggested_db_command = 'nucypher felix createdb'
        how_to_proceed_message = f'\nTo initialize a new faucet database run:'
        emitter(message=how_to_proceed_message, color='green')
        emitter(message=f'\n\'{suggested_db_command}\'', color='green')

    # Ursula
    elif character_name == 'ursula' and not federated_only:
        suggested_staking_command = f'nucypher ursula stake'
        how_to_stake_message = f"\nTo initialize a NU stake, run '{suggested_staking_command}' or"
        emitter(message=how_to_stake_message, color='green')

    # Everyone: Give the use a suggestion as to what to do next
    vowles = ('a', 'e', 'i', 'o', 'u')
    character_name_starts_with_vowel = character_name[0].lower() in vowles
    adjective = 'an' if character_name_starts_with_vowel else 'a'
    suggested_command = f'nucypher {character_name} run'
    how_to_run_message = f"\nTo run {adjective} {character_name.capitalize()} node from the default configuration filepath run: \n\n'{suggested_command}'\n"

    if config_root is not None:
        config_file_location = os.path.join(config_root, config_file or character_config_class.CONFIG_FILENAME)
        suggested_command += ' --config-file {}'.format(config_file_location)

    return emitter(message=how_to_run_message.format(suggested_command), color='green')


def build_fleet_state_status(ursula) -> str:
    # Build FleetState status line
    if ursula.known_nodes.checksum is not NO_KNOWN_NODES:
        fleet_state_checksum = ursula.known_nodes.checksum[:7]
        fleet_state_nickname = ursula.known_nodes.nickname
        fleet_state_icon = ursula.known_nodes.icon
        fleet_state = '{checksum} ⇀{nickname}↽ {icon}'.format(icon=fleet_state_icon,
                                                              nickname=fleet_state_nickname,
                                                              checksum=fleet_state_checksum)
    elif ursula.known_nodes.checksum is NO_KNOWN_NODES:
        fleet_state = 'No Known Nodes'
    else:
        fleet_state = 'Unknown'

    return fleet_state


def paint_node_status(ursula, start_time):

    # Build Learning status line
    learning_status = "Unknown"
    if ursula._learning_task.running:
        learning_status = "Learning at {}s Intervals".format(ursula._learning_task.interval)
    elif not ursula._learning_task.running:
        learning_status = "Not Learning"

    teacher = 'Current Teacher ..... No Teacher Connection'
    if ursula._current_teacher_node:
        teacher = 'Current Teacher ..... {}'.format(ursula._current_teacher_node)

    # Build FleetState status line
    fleet_state = build_fleet_state_status(ursula=ursula)

    stats = ['⇀URSULA {}↽'.format(ursula.nickname_icon),
             '{}'.format(ursula),
             'Uptime .............. {}'.format(maya.now() - start_time),
             'Start Time .......... {}'.format(start_time.slang_time()),
             'Fleet State.......... {}'.format(fleet_state),
             'Learning Status ..... {}'.format(learning_status),
             'Learning Round ...... Round #{}'.format(ursula._learning_round),
             'Operating Mode ...... {}'.format('Federated' if ursula.federated_only else 'Decentralized'),
             'Rest Interface ...... {}'.format(ursula.rest_url()),
             'Node Storage Type ... {}'.format(ursula.node_storage._name.capitalize()),
             'Known Nodes ......... {}'.format(len(ursula.known_nodes)),
             'Work Orders ......... {}'.format(len(ursula._work_orders)),
             teacher]

    if not ursula.federated_only and ursula.stakes:
        total_staked = f'Total Staked ........ {ursula.total_staked} NU-wei'
        stats.append(total_staked)

        current_period = f'Current Period ...... {ursula.miner_agent.get_current_period()}'
        stats.append(current_period)

    click.echo('\n' + '\n'.join(stats) + '\n')


def paint_known_nodes(ursula) -> None:
    # Gather Data
    known_nodes = ursula.known_nodes
    number_of_known_nodes = len(ursula.node_storage.all(federated_only=ursula.federated_only))
    seen_nodes = len(ursula.node_storage.all(federated_only=ursula.federated_only, certificates_only=True))

    # Operating Mode
    federated_only = ursula.federated_only
    if federated_only:
        click.secho("Configured in Federated Only mode", fg='green')

    # Heading
    label = "Known Nodes (connected {} / seen {})".format(number_of_known_nodes, seen_nodes)
    heading = '\n' + label + " " * (45 - len(label))
    click.secho(heading, bold=True, nl=True)

    # Build FleetState status line
    fleet_state = build_fleet_state_status(ursula=ursula)
    fleet_status_line = 'Fleet State {}'.format(fleet_state)
    click.secho(fleet_status_line, fg='blue', bold=True, nl=True)

    # Legend
    color_index = {
        'self': 'yellow',
        'known': 'white',
        'seednode': 'blue'
    }

    # Ledgend
    # for node_type, color in color_index.items():
    #     click.secho('{0:<6} | '.format(node_type), fg=color, nl=False)
    # click.echo('\n')

    seednode_addresses = list(bn.checksum_address for bn in SEEDNODES)

    for node in known_nodes:
        row_template = "{} | {}"
        node_type = 'known'
        if node.checksum_public_address == ursula.checksum_public_address:
            node_type = 'self'
            row_template += ' ({})'.format(node_type)
        elif node.checksum_public_address in seednode_addresses:
            node_type = 'seednode'
            row_template += ' ({})'.format(node_type)
        click.secho(row_template.format(node.rest_url().ljust(20), node), fg=color_index[node_type])


def paint_contract_status(ursula_config, click_config):
    contract_payload = """

    | NuCypher ETH Contracts |

    Provider URI ............. {provider_uri}
    Registry Path ............ {registry_filepath}

    NucypherToken ............ {token}
    MinerEscrow .............. {escrow}
    PolicyManager ............ {manager}

    """.format(provider_uri=ursula_config.blockchain.interface.provider_uri,
               registry_filepath=ursula_config.blockchain.interface.registry.filepath,
               token=ursula_config.token_agent.contract_address,
               escrow=ursula_config.miner_agent.contract_address,
               manager=ursula_config.policy_agent.contract_address,
               period=ursula_config.miner_agent.get_current_period())
    click.secho(contract_payload)

    network_payload = """
    | Blockchain Network |

    Current Period ........... {period}
    Gas Price ................ {gas_price}
    Active Staking Ursulas ... {ursulas}

    """.format(period=click_config.miner_agent.get_current_period(),
               gas_price=click_config.blockchain.interface.w3.eth.gasPrice,
               ursulas=click_config.miner_agent.get_miner_population())
    click.secho(network_payload)


def paint_staged_stake(ursula,
                       stake_value,
                       duration,
                       start_period,
                       end_period,
                       division_message: str = None):

    if division_message:
        click.secho(f"\n{'=' * 30} ORIGINAL STAKE {'=' * 28}", bold=True)
        click.secho(division_message)

    click.secho(f"\n{'=' * 30} STAGED STAKE {'=' * 30}", bold=True)

    click.echo(f"""
{ursula}
~ Value      -> {stake_value} ({Decimal(int(stake_value)):.2E} NuNit)
~ Duration   -> {duration} Days ({duration} Periods)
~ Enactment  -> {datetime_at_period(period=start_period)} (period #{start_period})
~ Expiration -> {datetime_at_period(period=end_period)} (period #{end_period})
    """)

    click.secho('=========================================================================', bold=True)


def paint_staking_confirmation(ursula, transactions):
    click.secho(f'\nEscrow Address ... {ursula.miner_agent.contract_address}', fg='blue')
    for tx_name, txhash in transactions.items():
        click.secho(f'{tx_name.capitalize()} .......... {txhash.hex()}', fg='green')
    click.secho(f'''

Successfully transmitted stake initialization transactions.

View your active stakes by running 'nucypher ursula stake --list'
or start your Ursula node by running 'nucypher ursula run'.
''', fg='green')


def prettify_stake(stake_index: int, stake) -> str:

    start_datetime = str(stake.start_datetime.slang_date())
    expiration_datetime = str(stake.end_datetime.slang_date())
    duration = stake.duration

    pretty_periods = f'{duration} periods {"." if len(str(duration)) == 2 else ""}'
    pretty = f'| {stake_index} | {pretty_periods} | {start_datetime} .. | {expiration_datetime} ... | {str(stake.value)}'
    return pretty


def paint_stakes(stakes):
    header = f'| # | Duration     | Enact       | Expiration | Value '
    breaky = f'| - | ------------ | ----------- | -----------| ----- '
    click.secho(header, bold=True)
    click.secho(breaky, bold=True)
    for index, stake in stakes.items():
        row = prettify_stake(stake_index=index, stake=stake)
        click.echo(row)
    return


def paint_staged_stake_division(ursula,
                                original_index,
                                original_stake,
                                target_value,
                                extension):

    new_end_period = original_stake.end_period + extension
    new_duration = new_end_period - original_stake.start_period

    division_message = f"""
{ursula}
~ Original Stake: {prettify_stake(stake_index=original_index, stake=original_stake)}
"""

    paint_staged_stake(ursula=ursula,
                       stake_value=target_value,
                       duration=new_duration,
                       start_period=original_stake.start_period,
                       end_period=new_end_period,
                       division_message=division_message)
