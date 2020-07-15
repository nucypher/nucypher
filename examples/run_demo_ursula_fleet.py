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
from contextlib import suppress
from functools import partial

from twisted.internet import reactor

from constant_sorrow.constants import TEMPORARY_DOMAIN
from nucypher.characters.lawful import Ursula

FLEET_POPULATION = 12
DEMO_NODE_STARTING_PORT = 11500

ursula_maker = partial(Ursula, rest_host='127.0.0.1',
                       federated_only=True,
                       domains=[TEMPORARY_DOMAIN]
                       )


def spin_up_federated_ursulas(quantity: int = FLEET_POPULATION):
    # Ports
    starting_port = DEMO_NODE_STARTING_PORT
    ports = list(map(str, range(starting_port, starting_port + quantity)))

    ursulas = []

    sage = ursula_maker(
        rest_port=ports[0],
        db_filepath="sage.db",
    )

    ursulas.append(sage)
    for index, port in enumerate(ports[1:]):
        u = ursula_maker(
            rest_port=port,
            seed_nodes=[sage.seed_node_metadata()],
            start_learning_now=True,
            db_filepath=f"{port}.db",
        )
        ursulas.append(u)
    for u in ursulas:
        deployer = u.get_deployer()
        deployer.addServices()
        deployer.catalogServers(deployer.hendrix)
        deployer.start()
        print(f"{u}: {deployer._listening_message()}")
    try:
        reactor.run()  # GO!
    finally:
        with suppress(FileNotFoundError):
            os.remove("sage.db")
        for u in ursulas[1:]:
            with suppress(FileNotFoundError):
                os.remove(f"{u.rest_interface.port}.db")


if __name__ == "__main__":
    spin_up_federated_ursulas()
