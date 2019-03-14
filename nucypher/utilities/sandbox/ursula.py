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
from eth_utils import to_checksum_address
from typing import Union, Set, List

from nucypher.blockchain.eth.constants import MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS, MAX_MINTING_PERIODS
from nucypher.characters.lawful import Ursula
from nucypher.config.characters import UrsulaConfiguration
from nucypher.crypto.api import secure_random
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

        port = ursula.rest_information()[0].port
        MOCK_KNOWN_URSULAS_CACHE[port] = ursula

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
                               **ursula_overrides) -> List[Ursula]:

    # Alternately accepts an int of the quantity of ursulas to make
    if isinstance(ether_addresses, int):
        ether_addresses = [to_checksum_address(secure_random(20)) for _ in range(ether_addresses)]

    if not MOCK_KNOWN_URSULAS_CACHE:
        starting_port = MOCK_URSULA_STARTING_PORT
    else:
        starting_port = max(MOCK_KNOWN_URSULAS_CACHE.keys()) + 1

    ursulas = list()
    for port, checksum_address in enumerate(ether_addresses, start=starting_port):

        ursula = ursula_config.produce(checksum_public_address=checksum_address,
                                       db_filepath=MOCK_URSULA_DB_FILEPATH,
                                       rest_port=port + 100,
                                       **ursula_overrides)
        if stake is True:

            min_stake, balance = MIN_ALLOWED_LOCKED, ursula.token_balance
            amount = random.randint(min_stake, balance)

            # for a random lock duration
            min_locktime, max_locktime = MIN_LOCKED_PERIODS, MAX_MINTING_PERIODS
            periods = random.randint(min_locktime, max_locktime)

            ursula.initialize_stake(amount=amount, lock_periods=periods)

        ursulas.append(ursula)
        # Store this Ursula in our global cache.
        port = ursula.rest_information()[0].port
        MOCK_KNOWN_URSULAS_CACHE[port] = ursula

    if know_each_other:

        for ursula_to_teach in ursulas:
            # Add other Ursulas as known nodes.
            for ursula_to_learn_about in ursulas:
                ursula_to_teach.remember_node(ursula_to_learn_about)

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
