
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


from collections import deque

import maya
import os
from twisted.internet import reactor
from twisted.internet.protocol import connectionDone
from twisted.internet.stdio import StandardIO
from twisted.protocols.basic import LineReceiver

from nucypher.utilities.logging import Logger


class UrsulaCommandProtocol(LineReceiver):

    encoding = 'utf-8'
    delimiter = os.linesep.encode(encoding=encoding)

    def __init__(self, ursula, emitter):
        super().__init__()

        self.ursula = ursula
        self.emitter = emitter
        self.start_time = maya.now()

        self.__history = deque(maxlen=10)
        self.prompt = bytes('Ursula({}) >>> '.format(self.ursula.checksum_address[:9]), encoding='utf-8')

        # Expose Ursula functional entry points
        self.__commands = {

            # Help
            '?': self.paintHelp,
            'help': self.paintHelp,

            # Status
            'status': self.paintStatus,
            'known_nodes': self.paintKnownNodes,
            'fleet_state': self.paintFleetState,

            # Learning Control
            'cycle_teacher': self.cycle_teacher,
            'start_learning': self.start_learning,
            'stop_learning': self.stop_learning,

            # Process Control
            'stop': self.stop,

        }

        self._hidden_commands = ('?',)

    @property
    def commands(self):
        return self.__commands.keys()

    def paintHelp(self):
        """
        Display this help message.
        """
        self.emitter.echo("\nUrsula Command Help\n===================\n")
        for command, func in self.__commands.items():
            if command not in self._hidden_commands:
                try:
                    self.emitter.echo(f'{command}\n{"-"*len(command)}\n{func.__doc__.lstrip()}')
                except AttributeError:
                    raise AttributeError("Ursula Command method is missing a docstring,"
                                         " which is required for generating help text.")

    def paintKnownNodes(self):
        """
        Display a list of all known nucypher peers.
        """
        from nucypher.cli.painting.nodes import paint_known_nodes
        paint_known_nodes(emitter=self.emitter, ursula=self.ursula)

    def paintStakes(self):
        """
        Display a list of all active stakes.
        """
        if self.ursula.stakes:
            from nucypher.cli.painting.staking import paint_stakes
            paint_stakes(self.emitter, stakes=self.ursula.stakes)
        else:
            self.emitter.echo("No active stakes.")

    def paintStatus(self):
        """
        Display the current status of the attached Ursula node.
        """
        from nucypher.cli.painting.nodes import paint_node_status
        paint_node_status(emitter=self.emitter, ursula=self.ursula, start_time=self.start_time)

    def paintFleetState(self):
        """
        Display information about the network-wide fleet state as the attached Ursula node sees it.
        """
        from nucypher.cli.painting.nodes import build_fleet_state_status
        self.emitter.echo(build_fleet_state_status(ursula=self.ursula))

    def connectionMade(self):
        self.emitter.echo("\nType 'help' or '?' for help")
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
                self.emitter.echo("Invalid input")
                self.__commands["?"]()

        else:
            self.__history.append(raw_line)

        # Loop
        self.transport.write(self.prompt)

    def cycle_teacher(self):
        """
        Manually direct the attached Ursula node to start learning from a different teacher.
        """
        return self.ursula.cycle_teacher_node()

    def start_learning(self):
        """
        Manually start the attached Ursula's node learning protocol.
        """
        return self.ursula.start_learning_loop()

    def stop_learning(self):
        """
        Manually stop the attached Ursula's node learning protocol.
        """
        return self.ursula.stop_learning_loop()

    def stop(self):
        """
        Shutdown the attached running Ursula node.
        """
        return reactor.stop()


class JSONRPCLineReceiver(LineReceiver):

    encoding = 'utf-8'
    delimiter = os.linesep.encode(encoding=encoding)
    __ipc_endpoint = "/tmp/nucypher.ipc"

    class IPCWriter(StandardIO):
        pass

    def __init__(self, rpc_controller, capture_output: bool = False):
        super().__init__()

        self.rpc_controller = rpc_controller
        self.start_time = maya.now()

        self.__captured_output = list()
        self.capture_output = capture_output

        self.__ipc_fd = None
        self.__ipc_writer = None

        self.log = Logger(f"JSON-RPC-{rpc_controller.app_name}")  # TODO needs ID

    @property
    def captured_output(self):
        return self.__captured_output

    def connectionMade(self):

        self.__ipc_fd = open(self.__ipc_endpoint, 'ab+')
        self.__ipc_writer = self.__ipc_fd.write

        # Hookup the IPC endpoint file
        self.transport.write = self.__ipc_writer

        self.log.info(f"JSON RPC-IPC endpoint opened at {self.__ipc_endpoint}."
                      f" Listening for messages.")  # TODO

    def connectionLost(self, reason=connectionDone) -> None:
        self.__ipc_fd.close()
        os.remove(self.__ipc_endpoint)

        self.log.info("JSON RPC-IPC Endpoint Closed.")  # TODO

    def rawDataReceived(self, data):
        pass

    def lineReceived(self, line):
        line = line.strip(self.delimiter)
        if line:
            self.rpc_controller.handle_request(control_request=line)
