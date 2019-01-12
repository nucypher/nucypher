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


# WARNING This is not a mining script!
# you will not perform any re-encryptions, and you will not get paid.
# It might be (but might not be) useful for determining whether you have
# the proper dependencies and configuration to run an actual mining node.


import os

from twisted.internet import protocol
from twisted.internet import reactor
from twisted.logger import globalLogPublisher

from nucypher.utilities.logging import SimpleObserver


FLEET_POPULATION = 2


def spin_up_federated_ursulas(quantity: int = FLEET_POPULATION):

    # Logger
    globalLogPublisher.addObserver(SimpleObserver())

    # Ports
    starting_port = 11501
    ports = map(str, range(starting_port, starting_port + quantity))

    ursula_processes = list()
    for index, port in enumerate(ports):

        teacher_uri = '127.0.0.1:{}'.format(int(port) - 1)

        args = ['nucypher',
                'ursula', 'run',
                '--rest-port', port,
                '--teacher-uri', teacher_uri,
                '--federated-only',
                '--dev',
                '--debug',
                '--config-root', 'demo-ursula-{}'.format(port)
                ]

        env = {'PATH': os.environ['PATH'],
               'NUCYPHER_SENTRY_LOGS': '0',
               'NUCYPHER_FILE_LOGS': '0',
               'LC_ALL': 'C.UTF-8',
               'LANG': 'C.UTF-8'}

        childFDs = {0: 0,
                    1: 1,
                    2: 2}

        class UrsulaProcessProtocol(protocol.Protocol):

            def __init__(self, command):
                self.command = command

        processProtocol = UrsulaProcessProtocol(command=args)
        p = reactor.spawnProcess(processProtocol, 'nucypher', args, env=env, childFDs=childFDs)
        ursula_processes.append(p)

        reactor.run()  # GO!


if __name__ == "__main__":
    spin_up_federated_ursulas()

