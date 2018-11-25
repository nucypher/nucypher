"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import click
import maya

import nucypher
from constant_sorrow.constants import NO_KNOWN_NODES
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import SEEDNODES

#
# Art
#

BANNER = """
                                  _               
                                 | |              
     _ __  _   _  ___ _   _ _ __ | |__   ___ _ __ 
    | '_ \| | | |/ __| | | | '_ \| '_ \ / _ \ '__|
    | | | | |_| | (__| |_| | |_) | | | |  __/ |   
    |_| |_|\__,_|\___|\__, | .__/|_| |_|\___|_|   
                       __/ | |                    
                      |___/|_|  

    version {}

""".format(nucypher.__version__)


#
# Paint
#

def paint_configuration(config_filepath: str) -> None:
    json_config = UrsulaConfiguration._read_configuration_file(filepath=config_filepath)
    click.secho("\n======== Ursula Configuration ======== \n", bold=True)
    for key, value in json_config.items():
        click.secho("{} = {}".format(key, value))


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
    if ursula.known_nodes.checksum is not NO_KNOWN_NODES:
        fleet_state_checksum = ursula.known_nodes.checksum[:7]
        fleet_state_nickname = ursula.known_nodes.nickname
        fleet_state_icon = ursula.known_nodes.icon
        fleet_state = '{2} {1} ({0})'.format(fleet_state_checksum, fleet_state_nickname, fleet_state_icon)
    elif ursula.known_nodes.checksum is not NO_KNOWN_NODES:
        fleet_state = 'No Known Nodes'
    else:
        fleet_state = 'Unknown'

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
    heading = '\n' + label + " " * (45 - len(label)) + "Last Seen    "
    click.secho(heading, bold=True, nl=False)

    # Legend
    color_index = {
        'self': 'yellow',
        'known': 'white',
        'seednode': 'blue'
    }
    for node_type, color in color_index.items():
        click.secho('{0:<6} | '.format(node_type), fg=color, nl=False)
    click.echo('\n')

    seednode_addresses = list(bn.checksum_address for bn in SEEDNODES)

    for node in known_nodes:
        row_template = "{} | {} | {} | {} | {}"
        node_type = 'known'
        if node.checksum_public_address == ursula.checksum_public_address:
            node_type = 'self'
            row_template += ' ({})'.format(node_type)
        elif node.checksum_public_address in seednode_addresses:
            node_type = 'seednode'
            row_template += ' ({})'.format(node_type)
        click.secho(row_template.format(node.checksum_public_address,
                                        node.rest_url().ljust(20),
                                        node.nickname.ljust(50),
                                        node.timestamp,
                                        node.last_seen,
                                        ), fg=color_index[node_type])
