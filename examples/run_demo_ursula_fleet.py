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

import os
from contextlib import suppress
from functools import partial
from pathlib import Path

from twisted.internet import reactor

from nucypher.characters.lawful import Ursula
from nucypher.config.constants import APP_DIR, TEMPORARY_DOMAIN
from nucypher.utilities.networking import LOOPBACK_ADDRESS

FLEET_POPULATION = 12
DEMO_NODE_STARTING_PORT = 11500

ursula_maker = partial(Ursula, rest_host=LOOPBACK_ADDRESS,
                       federated_only=True,
                       domain=TEMPORARY_DOMAIN)


def spin_up_federated_ursulas(quantity: int = FLEET_POPULATION):
    # Ports
    starting_port = DEMO_NODE_STARTING_PORT
    ports = list(map(str, range(starting_port, starting_port + quantity)))
    sage_dir = str(Path(APP_DIR.user_cache_dir) / 'sage.db')
    ursulas = []

    if not os.path.exists(sage_dir):
        os.makedirs(sage_dir)

    sage = ursula_maker(rest_port=ports[0], db_filepath=sage_dir)

    ursulas.append(sage)
    for index, port in enumerate(ports[1:]):
        u = ursula_maker(
            rest_port=port,
            seed_nodes=[sage.seed_node_metadata()],
            start_learning_now=True,
            db_filepath=f"{Path(APP_DIR.user_cache_dir) / port}.db",
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
