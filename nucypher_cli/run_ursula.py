import asyncio

import click

from nucypher.characters import Ursula
from nucypher_cli.metadata import collect_stored_nodes, write_node_metadata

RUNTIME_DIR = './.nucypher'


@click.option('--rest-port', type=int)
@click.option('--dht-port', type=int)
@click.option('--db-name')
@click.option('--checksum-address', type=hex)
@click.option('--stake-index', type=int)
@click.option('--metadata-dir')
@click.command()
def run_ursula(rest_port, dht_port, db_name, checksum_address, stake_index, metadata_dir) -> None:
    """
    ======================================

    ~ WARNING: DO NOT USE THIS TO MINE ~

    This is not an actual mining script -
    it is a twisted process handler

    ======================================


    This process handler is executed in the main thread using the nucypher-cli,
    implemented with twisted ProcessProtocol and spawnProcess.

    The following procedure is required to "spin-up" an Ursula node.

        1. Collect all known known from storages
        2. Start the asyncio event loop
        3. Initialize Ursula object
        4. Start DHT listener
        5. Enter the learning loop
        6. Run TLS deployment
        7. Start the staking daemon

    Configurable values are first read from the .ini configuration file,
    but can be overridden (mostly for testing purposes) with inline cli options.

    """

    known_nodes, other_nodes = collect_stored_nodes()  # 1. Collect known nodes
    asyncio.set_event_loop(asyncio.new_event_loop())   # 2. Init DHT async loop

    # 3. Initialize Ursula (includes overrides)
    ursula = Ursula.from_config(known_nodes=known_nodes,
                                rest_port=rest_port,
                                dht_port=dht_port,
                                db_name=db_name,
                                checksum_address=checksum_address,
                                stake_index=stake_index)

    ursula.dht_listen()           # 4. Start DHT
    write_node_metadata(node=ursula, node_metadata_dir=metadata_dir)

    ursula.start_learning_loop()  # 5. Enter learning loop
    ursula.get_deployer().run()   # 6. Run TLS Deployer

    # ursula.stake()              # TODO: 7. start staking daemon


if __name__ == "__main__":
    run_ursula()
