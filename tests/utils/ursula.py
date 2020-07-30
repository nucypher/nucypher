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


import contextlib

import socket

from cryptography.x509 import Certificate
from typing import Iterable, List, Optional, Set

from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.characters.lawful import Ursula
from nucypher.config.characters import UrsulaConfiguration
from nucypher.crypto.powers import TransactingPower
from tests.constants import (
    MOCK_URSULA_DB_FILEPATH,
    NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK
)


def select_test_port() -> int:
    """
    Search for a network port that is open at the time of the call;
    Verify that the port is not the same as the default Ursula running port.

    Note: There is no guarantee that the returned port will still be available later.
    """

    closed_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with contextlib.closing(closed_socket) as open_socket:
        open_socket.bind(('localhost', 0))
        port = open_socket.getsockname()[1]

        if port == UrsulaConfiguration.DEFAULT_REST_PORT or port > 64000:
            return select_test_port()

        open_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return port


def make_federated_ursulas(ursula_config: UrsulaConfiguration,
                           quantity: int = NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
                           know_each_other: bool = True,
                           **ursula_overrides) -> Set[Ursula]:

    if not MOCK_KNOWN_URSULAS_CACHE:
        starting_port = MOCK_URSULA_STARTING_PORT
    else:
        starting_port = max(MOCK_KNOWN_URSULAS_CACHE.keys()) + 1

    federated_ursulas = set()
    for port in range(starting_port, starting_port+quantity):

        ursula = ursula_config.produce(rest_port=port + 100,
                                       db_filepath=MOCK_URSULA_DB_FILEPATH,
                                       **ursula_overrides)

        federated_ursulas.add(ursula)

        # Store this Ursula in our global testing cache.

        port = ursula.rest_interface.port
        MOCK_KNOWN_URSULAS_CACHE[port] = ursula

    if know_each_other:
        for ursula_to_teach in federated_ursulas:
            # Add other Ursulas as known nodes.
            for ursula_to_learn_about in federated_ursulas:
                ursula_to_teach.remember_node(ursula_to_learn_about)

    return federated_ursulas


def make_decentralized_ursulas(ursula_config: UrsulaConfiguration,
                               stakers_addresses: Iterable[str],
                               workers_addresses: Iterable[str],
                               commit_to_next_period: bool = False,
                               **ursula_overrides) -> List[Ursula]:

    if not MOCK_KNOWN_URSULAS_CACHE:
        starting_port = MOCK_URSULA_STARTING_PORT
    else:
        starting_port = max(MOCK_KNOWN_URSULAS_CACHE.keys()) + 1

    stakers_and_workers = zip(stakers_addresses, workers_addresses)
    ursulas = list()

    for port, (staker_address, worker_address) in enumerate(stakers_and_workers, start=starting_port):
        ursula = ursula_config.produce(checksum_address=staker_address,
                                       worker_address=worker_address,
                                       db_filepath=MOCK_URSULA_DB_FILEPATH,
                                       rest_port=port + 100,
                                       **ursula_overrides)
        if commit_to_next_period:
            # TODO: Is _crypto_power trying to be public?  Or is there a way to expose *something* public about TransactingPower?
            # Do we need to revisit the concept of "public material"?  Or does this rightly belong as a method?
            tx_power = ursula._crypto_power.power_ups(TransactingPower)
            tx_power.activate()
            ursula.commit_to_next_period()

        ursulas.append(ursula)
        # Store this Ursula in our global cache.
        port = ursula.rest_interface.port
        MOCK_KNOWN_URSULAS_CACHE[port] = ursula

    return ursulas


def make_ursula_for_staker(staker: Staker,
                           worker_address: str,
                           blockchain: BlockchainInterface,
                           ursula_config: UrsulaConfiguration,
                           ursulas_to_learn_about: Optional[List[Ursula]] = None,
                           commit_to_next_period: bool = False,
                           **ursula_overrides) -> Ursula:

    # Assign worker to this staker
    staker.bond_worker(worker_address=worker_address)

    worker = make_decentralized_ursulas(ursula_config=ursula_config,
                                        blockchain=blockchain,
                                        stakers_addresses=[staker.checksum_address],
                                        workers_addresses=[worker_address],
                                        commit_to_next_period=commit_to_next_period,
                                        **ursula_overrides).pop()

    for ursula_to_learn_about in (ursulas_to_learn_about or []):
        worker.remember_node(ursula_to_learn_about)
        ursula_to_learn_about.remember_node(worker)

    return worker


def start_pytest_ursula_services(ursula: Ursula) -> Certificate:
    """
    Takes an ursula and starts its learning
    services when running tests with pytest twisted.
    """

    node_deployer = ursula.get_deployer()

    node_deployer.addServices()
    node_deployer.catalogServers(node_deployer.hendrix)
    node_deployer.start()

    certificate_as_deployed = node_deployer.cert.to_cryptography()
    return certificate_as_deployed


MOCK_KNOWN_URSULAS_CACHE = dict()
MOCK_URSULA_STARTING_PORT = select_test_port()
