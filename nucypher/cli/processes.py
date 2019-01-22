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
from twisted.internet.protocol import connectionDone
from twisted.protocols.basic import LineReceiver

from nucypher.cli.painting import build_fleet_state_status


class UrsulaCommandProtocol(LineReceiver):

    encoding = 'utf-8'
    delimiter = os.linesep.encode(encoding=encoding)

    def __init__(self, ursula):
        super().__init__()

        self.ursula = ursula
        self.start_time = maya.now()

        self.__history = deque(maxlen=10)
        self.prompt = bytes('Ursula({}) >>> '.format(self.ursula.checksum_public_address[:9]), encoding='utf-8')

        # Expose Ursula functional entry points
        self.__commands = {

            # Status
            'status': self.paintStatus,
            'known_nodes': self.paintKnownNodes,
            'fleet_state': self.paintFleetState,

            # Learning Control
            'cycle_teacher': self.ursula.cycle_teacher_node,
            'start_learning': self.ursula.start_learning_loop,
            'stop_learning': self.ursula.stop_learning_loop,

            # Process Control
            'stop': reactor.stop,

        }

    @property
    def commands(self):
        return self.__commands.keys()

    def paintKnownNodes(self):
        from nucypher.cli.painting import paint_known_nodes
        paint_known_nodes(ursula=self.ursula)

    def paintStatus(self):
        from nucypher.cli.painting import paint_node_status
        paint_node_status(ursula=self.ursula, start_time=self.start_time)

    def paintFleetState(self):
        line = '{}'.format(build_fleet_state_status(ursula=self.ursula))
        click.secho(line)

    def connectionMade(self):

        message = 'Attached {}@{}'.format(
                   self.ursula.checksum_public_address,
                   self.ursula.rest_url())

        click.secho(message, fg='green')
        click.secho('{} | {}'.format(self.ursula.nickname_icon, self.ursula.nickname), fg='blue', bold=True)

        click.secho("\nType 'help' or '?' for help")
        self.transport.write(self.prompt)

    def connectionLost(self, reason=connectionDone) -> None:
        self.ursula.stop_learning_loop(reason=reason)

    def lineReceived(self, line):
        """Ursula Console REPL"""

        # Read
        raw_line = line.decode(encoding=self.encoding)
        line = raw_line.strip().lower()

        # Evaluate
        try:
            self.__commands[line]()

        # Print
        except KeyError:
            if line:  # allow for empty string
                click.secho("Invalid input. Options are {}".format(', '.join(self.__commands.keys())))

        else:
            self.__history.append(raw_line)

        # Loop
        self.transport.write(self.prompt)
