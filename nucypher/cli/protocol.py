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


import os
from collections import deque

import click
import maya
from twisted.internet import reactor
from twisted.protocols.basic import LineReceiver

from nucypher.config.constants import SEEDNODES


class UrsulaCommandProtocol(LineReceiver):

    encoding = 'utf-8'
    delimiter = os.linesep.encode(encoding=encoding)

    def __init__(self, ursula):
        self.ursula = ursula
        self.start_time = maya.now()
        self.prompt = bytes('Ursula({}) >>> '.format(self.ursula.checksum_public_address[:9]), encoding='utf-8')
        super().__init__()

    def _paint_known_nodes(self):
        # Gather Data
        known_nodes = self.ursula.known_nodes
        known_certificate_files = os.listdir(self.ursula.known_certificates_dir)
        number_of_known_nodes = len(known_nodes)
        seen_nodes = len(known_certificate_files)

        # Operating Mode
        federated_only = self.ursula.federated_only
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
        for address, node in known_nodes.items():
            row_template = "{} | {} | {} | {} | {}"
            node_type = 'known'
            if node.checksum_public_address == self.ursula.checksum_public_address:
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

    def paintStatus(self):

        if self.ursula._learning_task.running:
            learning_status = "Learning at {}s Intervals".format(self.ursula._learning_task.interval)
        elif not self.ursula._learning_task.running:
            learning_status = "Not Learning"
        else:
            learning_status = "Unknown"

        if self.ursula._current_teacher_node:
            teacher = 'Current Teacher ..... {}'.format(self.ursula._current_teacher_node)
        else:
            teacher = 'Current Teacher ..... No Teacher Connection'

        stats = ['⇀URSULA {}↽'.format(self.ursula.nickname_icon),
                 '{}'.format(self.ursula),
                 'Uptime .............. {}'.format(maya.now() - self.start_time),
                 'Start Time .......... {}'.format(self.start_time.slang_time()),
                 'Fleet State ......... {2} {1} ({0})'.format(self.ursula.known_nodes.checksum[:7], self.ursula.known_nodes.nickname, self.ursula.known_nodes.icon),
                 'Learning Status ..... {}'.format(learning_status),
                 'Learning Round ...... Round #{}'.format(self.ursula._learning_round),
                 'Operating Mode ...... {}'.format('Federated' if self.ursula.federated_only else 'Decentralized'),
                 'Rest Interface ...... {}'.format(self.ursula.rest_url()),
                 'Node Storage Type ... {}'.format(self.ursula.node_storage._name.capitalize()),
                 'Known Nodes ......... {}'.format(len(self.ursula.known_nodes)),
                 'Work Orders ......... {}'.format(len(self.ursula._work_orders)),
                 teacher]

        click.echo('\n' + '\n'.join(stats) + '\n')

    def connectionMade(self):

        message = 'Attached {}@{}'.format(
                   self.ursula.checksum_public_address,
                   self.ursula.rest_url())

        click.secho(message, fg='green')
        click.secho('{} | {}'.format(self.ursula.nickname_icon, self.ursula.nickname), fg='blue', bold=True)

        click.secho("\nType 'help' or '?' for help")
        self.transport.write(self.prompt)

    def lineReceived(self, line):
        """Ursula REPL"""

        # Read
        line = line.decode(encoding=self.encoding).strip().lower()

        commands = {
            'known_nodes': self._paint_known_nodes,
            'status': self.paintStatus,
            'stop': reactor.stop,
            'cycle_teacher': self.ursula.cycle_teacher_node,
            'update_snapshot': self.ursula.update_snapshot,
            'start_learning': self.ursula.start_learning_loop,
            'stop_learning': self.ursula.stop_learning_loop
        }

        # Evaluate
        try:
            commands[line]()

        # Print
        except KeyError:
            if line:
                click.secho("Invalid input. Options are {}".format(', '.join(commands)))

        # Loop
        self.transport.write(self.prompt)
