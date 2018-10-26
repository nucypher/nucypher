import os
import random
import sys

import maya
import time
from os import linesep

import click
from eth_utils import to_checksum_address
from twisted.internet import reactor
from twisted.protocols.basic import LineReceiver
from typing import Set, Union

from nucypher.blockchain.eth import constants
from nucypher.characters.lawful import Ursula
from nucypher.config.characters import UrsulaConfiguration
from nucypher.crypto.api import secure_random
from nucypher.utilities.sandbox.constants import (DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
                                                  TEST_URSULA_STARTING_PORT,
                                                  TEST_KNOWN_URSULAS_CACHE)


def make_federated_ursulas(ursula_config: UrsulaConfiguration,
                           quantity: int = DEFAULT_NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
                           know_each_other: bool = True,
                           **ursula_overrides) -> Set[Ursula]:

    if not TEST_KNOWN_URSULAS_CACHE:
        starting_port = TEST_URSULA_STARTING_PORT
    else:
        starting_port = max(TEST_KNOWN_URSULAS_CACHE.keys()) + 1

    federated_ursulas = set()
    for port in range(starting_port, starting_port+quantity):

        ursula = ursula_config.produce(rest_port=port + 100,
                                       db_name="test-{}".format(port),
                                       **ursula_overrides)

        federated_ursulas.add(ursula)

        # Store this Ursula in our global testing cache.

        port = ursula.rest_information()[0].port
        TEST_KNOWN_URSULAS_CACHE[port] = ursula

    if know_each_other:

        for ursula_to_teach in federated_ursulas:
            # Add other Ursulas as known nodes.
            for ursula_to_learn_about in federated_ursulas:
                ursula_to_teach.remember_node(ursula_to_learn_about)

    return federated_ursulas


def make_decentralized_ursulas(ursula_config: UrsulaConfiguration,
                               ether_addresses: Union[list, int],
                               stake: bool = False,
                               know_each_other: bool = True,
                               **ursula_overrides) -> Set[Ursula]:

    # Alternately accepts an int of the quantity of ursulas to make
    if isinstance(ether_addresses, int):
        ether_addresses = [to_checksum_address(secure_random(20)) for _ in range(ether_addresses)]

    if not TEST_KNOWN_URSULAS_CACHE:
        starting_port = TEST_URSULA_STARTING_PORT
    else:
        starting_port = max(TEST_KNOWN_URSULAS_CACHE.keys()) + 1

    ursulas = set()
    for port, checksum_address in enumerate(ether_addresses, start=starting_port):

        ursula = ursula_config.produce(checksum_address=checksum_address,
                                       db_name="test-{}".format(port),
                                       rest_port=port + 100,
                                       **ursula_overrides)
        if stake is True:

            min_stake, balance = int(constants.MIN_ALLOWED_LOCKED), ursula.token_balance
            amount = random.randint(min_stake, balance)

            # for a random lock duration
            min_locktime, max_locktime = int(constants.MIN_LOCKED_PERIODS), int(constants.MAX_MINTING_PERIODS)
            periods = random.randint(min_locktime, max_locktime)

            ursula.initialize_stake(amount=amount, lock_periods=periods)

        ursulas.add(ursula)
        # Store this Ursula in our global cache.
        port = ursula.rest_information()[0].port
        TEST_KNOWN_URSULAS_CACHE[port] = ursula

    if know_each_other:

        for ursula_to_teach in ursulas:
            # Add other Ursulas as known nodes.
            for ursula_to_learn_about in ursulas:
                ursula_to_teach.remember_node(ursula_to_learn_about)

    return ursulas


class UrsulaCommandProtocol(LineReceiver):

    delimiter = linesep.encode("ascii")
    encoding = 'utf-8'

    width = 80
    height = 24

    commands = (
        'status',
        'stop',

    )

    def __init__(self, ursula):
        self.ursula = ursula
        self.start_time = maya.now()
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

        seednode_addresses = list(bn.checksum_address for bn in BOOTNODES)
        for address, node in known_nodes.items():
            row_template = "{} | {} | {}"
            node_type = 'known'
            if node.checksum_public_address == self.ursula.checksum_public_address:
                node_type = 'self'
                row_template += ' ({})'.format(node_type)
            if node.checksum_public_address in seednode_addresses:
                node_type = 'seednode'
                row_template += ' ({})'.format(node_type)
            click.secho(row_template.format(node.checksum_public_address,
                                            node.rest_url(),
                                            node.timestamp), fg=color_index[node_type])

    def paintStatus(self):
        stats = ['Ursula {}'.format(self.ursula.checksum_public_address),
                 '-'*50,
                 'Uptime: {}'.format(maya.now() - self.start_time), # TODO
                 'Learning Round: {}'.format(self.ursula._learning_round),
                 'Operating Mode: {}'.format('Federated' if self.ursula.federated_only else 'Decentralized'),  # TODO
                 'Rest Interface {}'.format(self.ursula.rest_url()),
                 'Node Storage Type {}:'.format(self.ursula.node_storage._name.capitalize()),
                 'Known Nodes: {}'.format(len(self.ursula.known_nodes)),
                 'Work Orders: {}'.format(len(self.ursula._work_orders))]

        if self.ursula._current_teacher_node:
            teacher = 'Current Teacher: {}@{}'.format(self.ursula._current_teacher_node.checksum_public_address,
                                                      self.ursula._current_teacher_node.rest_url())
            stats.append(teacher)

        click.echo('\n'+'\n'.join(stats))

    def connectionMade(self):
        message = '\nConnected to node console {}@{}'.format(self.ursula.checksum_public_address,
                                                             self.ursula.rest_url())
        click.secho(message, fg='yellow')
        click.secho("Type 'help' or '?' for help")
        self.transport.write(b'Ursula >>> ')

    def lineReceived(self, line):
        line = line.decode(encoding=self.encoding).strip().lower()

        commands = {
            'known_nodes': self._paint_known_nodes,
            'status': self.paintStatus,
            'stop': reactor.stop,
            'cycle_teacher': self.ursula.cycle_teacher_node
        }

        try:
            commands[line]()
        except KeyError:
            click.secho("Invalid input. Options are {}".format(', '.join(commands)))

        self.transport.write(b'Ursula >>> ')

    def terminalSize(self, width, height):
        self.width = width
        self.height = height
        self.terminal.eraseDisplay()
        self._redraw()


