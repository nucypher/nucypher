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

import random

from cryptography.x509 import Certificate
from typing import Set, List, Iterable

from nucypher.characters.lawful import Ursula
from nucypher.config.characters import UrsulaConfiguration
from nucypher.utilities.sandbox.constants import (
    MOCK_KNOWN_URSULAS_CACHE,
    MOCK_URSULA_STARTING_PORT,
    NUMBER_OF_URSULAS_IN_DEVELOPMENT_NETWORK,
    MOCK_URSULA_DB_FILEPATH)


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

        port = ursula.rest_interface().port
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
                               confirm_activity: bool = False,
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
        if confirm_activity:
            ursula.confirm_activity()

        ursulas.append(ursula)
        # Store this Ursula in our global cache.
        port = ursula.rest_interface().port
        MOCK_KNOWN_URSULAS_CACHE[port] = ursula

    return ursulas


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
