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


import time
from decimal import Decimal

import click
import maya
from constant_sorrow.constants import NO_KNOWN_NODES

from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.characters.banners import NUCYPHER_BANNER, NU_BANNER
from nucypher.config.constants import SEEDNODES


def echo_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(NUCYPHER_BANNER, bold=True)
    ctx.exit()


def paint_new_installation_help(emitter, new_configuration):
    character_config_class = new_configuration.__class__
    character_name = character_config_class._NAME.lower()

    emitter.message("Generated keyring {}".format(new_configuration.keyring_root), color='green')
    emitter.message("Saved configuration file {}".format(new_configuration.config_file_location), color='green')

    # Felix
    if character_name == 'felix':
        suggested_db_command = 'nucypher felix createdb'
        how_to_proceed_message = f'\nTo initialize a new faucet database run:'
        emitter.echo(how_to_proceed_message, color='green')
        emitter.echo(f'\n\'{suggested_db_command}\'', color='green')

    # Ursula
    elif character_name == 'ursula' and not new_configuration.federated_only:
        how_to_stake_message = f"\nIf you haven't done it already, initialize a NU stake with 'nucypher stake' or"
        emitter.echo(how_to_stake_message, color='green')

    # Everyone: Give the use a suggestion as to what to do next
    vowels = ('a', 'e', 'i', 'o', 'u')
    character_name_starts_with_vowel = character_name[0].lower() in vowels
    adjective = 'an' if character_name_starts_with_vowel else 'a'
    suggested_command = f'nucypher {character_name} run'
    how_to_run_message = f"\nTo run {adjective} {character_name.capitalize()} node from the default configuration filepath run: \n\n'{suggested_command}'\n"

    emitter.echo(how_to_run_message.format(suggested_command), color='green')


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


def paint_node_status(emitter, ursula, start_time):

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

    if not ursula.federated_only:
        staking_address = 'Worker Address ...... {}'.format(ursula.worker_address)
        current_period = f'Current Period ...... {ursula.staking_agent.get_current_period()}'
        stats.extend([current_period, staking_address])

    emitter.echo('\n' + '\n'.join(stats) + '\n')


def paint_known_nodes(emitter, ursula) -> None:
    # Gather Data
    known_nodes = ursula.known_nodes
    number_of_known_nodes = len(ursula.node_storage.all(federated_only=ursula.federated_only))
    seen_nodes = len(ursula.node_storage.all(federated_only=ursula.federated_only, certificates_only=True))

    # Operating Mode
    federated_only = ursula.federated_only
    if federated_only:
        emitter.echo("Configured in Federated Only mode", color='green')

    # Heading
    label = "Known Nodes (connected {} / seen {})".format(number_of_known_nodes, seen_nodes)
    heading = '\n' + label + " " * (45 - len(label))
    emitter.echo(heading, bold=True)

    # Build FleetState status line
    fleet_state = build_fleet_state_status(ursula=ursula)
    fleet_status_line = 'Fleet State {}'.format(fleet_state)
    emitter.echo(fleet_status_line, color='blue', bold=True)

    # Legend
    color_index = {
        'self': 'yellow',
        'known': 'white',
        'seednode': 'blue'
    }

    # Legend
    # for node_type, color in color_index.items():
    #     emitter.echo('{0:<6} | '.format(node_type), color=color, nl=False)
    # emitter.echo('\n')

    seednode_addresses = list(bn.checksum_address for bn in SEEDNODES)

    for node in known_nodes:
        row_template = "{} | {}"
        node_type = 'known'
        if node.checksum_address == ursula.checksum_address:
            node_type = 'self'
            row_template += ' ({})'.format(node_type)
        elif node.checksum_address in seednode_addresses:
            node_type = 'seednode'
            row_template += ' ({})'.format(node_type)
        emitter.echo(row_template.format(node.rest_url().ljust(20), node), color=color_index[node_type])


def paint_contract_status(emitter, ursula_config):
    contract_payload = """

| NuCypher ETH Contracts |

Provider URI ............. {provider_uri}
Registry Path ............ {registry_filepath}

NucypherToken ............ {token}
StakingEscrow ............ {escrow}
PolicyManager ............ {manager}

    """.format(provider_uri=ursula_config.blockchain.provider_uri,
               registry_filepath=ursula_config.blockchain.registry.filepath,
               token=ursula_config.token_agent.contract_address,
               escrow=ursula_config.staking_agent.contract_address,
               manager=ursula_config.policy_agent.contract_address,
               period=ursula_config.staking_agent.get_current_period())
    emitter.echo(contract_payload)

    network_payload = """
| Blockchain Network |

Current Period ........... {period}
Gas Price ................ {gas_price}
Active Staking Ursulas ... {ursulas}

    """.format(period=ursula_config.staking_agent.get_current_period(),
               gas_price=ursula_config.blockchain.client.gasPrice,
               ursulas=ursula_config.staking_agent.get_staker_population())
    emitter.echo(network_payload)


def paint_staged_stake(emitter,
                       stakeholder,
                       staking_address,
                       stake_value,
                       duration,
                       start_period,
                       end_period,
                       division_message: str = None):

    if division_message:
        emitter.echo(f"\n{'=' * 30} ORIGINAL STAKE {'=' * 28}", bold=True)
        emitter.echo(division_message)

    emitter.echo(f"\n{'=' * 30} STAGED STAKE {'=' * 30}", bold=True)

    emitter.echo(f"""
Staking address: {staking_address}
~ Chain      -> ID # {stakeholder.blockchain.client.chain_id} | {stakeholder.blockchain.client.chain_name}
~ Value      -> {stake_value} ({Decimal(int(stake_value)):.2E} NuNits)
~ Duration   -> {duration} Days ({duration} Periods)
~ Enactment  -> {datetime_at_period(period=start_period)} (period #{start_period})
~ Expiration -> {datetime_at_period(period=end_period)} (period #{end_period})
    """)

    emitter.echo('=========================================================================', bold=True)


def paint_staking_confirmation(emitter, ursula, transactions):
    emitter.echo(f'\nEscrow Address ... {ursula.staking_agent.contract_address}', color='blue')
    for tx_name, receipt in transactions.items():
        emitter.echo(f'{tx_name.capitalize()} .......... {receipt["transactionHash"].hex()}', color='green')
    emitter.echo(f'''

Successfully transmitted stake initialization transactions.

View your stakes by running 'nucypher stake list'
or set your Ursula worker node address by running 'nucypher stake set-worker'.
''', color='green')


def prettify_stake(stake, index: int = None) -> str:

    start_datetime = str(stake.start_datetime.slang_date())
    expiration_datetime = str(stake.end_datetime.slang_date())
    duration = stake.duration

    pretty_periods = f'{duration} periods {"." if len(str(duration)) == 2 else ""}'

    pretty = f'| {index if index is not None else "-"} ' \
             f'| {stake.owner_address[:6]} ' \
             f'| {stake.worker_address[:6]} ' \
             f'| {stake.index} ' \
             f'| {str(stake.value)} ' \
             f'| {pretty_periods} ' \
             f'| {start_datetime} - {expiration_datetime} ' \

    return pretty


def paint_stakes(emitter, stakes):

    title = "=========================== Active Stakes ==============================\n"

    header = f'| ~ | Staker | Worker | # | Value    | Duration     | Enactment          '
    breaky = f'|   | ------ | ------ | - | -------- | ------------ | ------------------ '

    emitter.echo(title)
    emitter.echo(header, bold=True)
    emitter.echo(breaky, bold=True)
    for index, stake in enumerate(stakes):
        row = prettify_stake(stake=stake, index=index)
        row_color = 'yellow' if stake.worker_address == BlockchainInterface.NULL_ADDRESS else 'white'
        emitter.echo(row, color=row_color)
    emitter.echo('')  # newline


def paint_staged_stake_division(emitter,
                                stakeholder,
                                original_stake,
                                target_value,
                                extension):

    new_end_period = original_stake.end_period + extension
    new_duration = new_end_period - original_stake.start_period
    staking_address = original_stake.checksum_address

    division_message = f"""
Staking address: {staking_address}
~ Original Stake: {prettify_stake(stake=original_stake, index=None)}
"""

    paint_staged_stake(emitter=emitter,
                       stakeholder=stakeholder,
                       staking_address=staking_address,
                       stake_value=target_value,
                       duration=new_duration,
                       start_period=original_stake.start_period,
                       end_period=new_end_period,
                       division_message=division_message)


def paint_contract_deployment(emitter, contract_name: str, contract_address: str, receipts: dict):

    # TODO: switch to using an explicit emitter

    # Paint heading
    heading = f'\r{" "*80}\n{contract_name} ({contract_address})'
    emitter.echo(heading, bold=True)
    emitter.echo('*' * (42 + 3 + len(contract_name)))

    # Paint Transactions
    for tx_name, receipt in receipts.items():
        emitter.echo("OK", color='green', nl=False, bold=True)
        emitter.echo(" | {}".format(tx_name), color='yellow', nl=False)
        emitter.echo(" | {}".format(receipt['transactionHash'].hex()), color='yellow', nl=False)
        emitter.echo(" ({} gas)".format(receipt['cumulativeGasUsed']))
        emitter.echo("Block #{} | {}\n".format(receipt['blockNumber'], receipt['blockHash'].hex()))


def paint_staged_deployment(emitter, deployer) -> None:
    emitter.clear()
    emitter.banner(NU_BANNER)
    emitter.echo(f"Current Time ........ {maya.now().iso8601()}")
    emitter.echo(f"Web3 Provider ....... {deployer.blockchain.provider_uri}")
    emitter.echo(f"Block ............... {deployer.blockchain.client.block_number}")
    emitter.echo(f"Gas Price ........... {deployer.blockchain.client.gas_price}")
    emitter.echo(f"Deployer Address .... {deployer.checksum_address}")
    emitter.echo(f"ETH ................. {deployer.eth_balance}")
    emitter.echo(f"Chain ID ............ {deployer.blockchain.client.chain_id}")
    emitter.echo(f"Chain Name .......... {deployer.blockchain.client.chain_name}")

    # Ask - Last chance to gracefully abort. This step cannot be forced.
    emitter.echo("\nDeployment successfully staged. Take a deep breath. \n", color='green')


def paint_deployment_delay(emitter, delay: int = 3) -> None:
    emitter.echo(f"Starting deployment in {delay} seconds...", color='red')
    for i in range(delay)[::-1]:
        emitter.echo(f"{i}...", color='yellow')
        time.sleep(1)
