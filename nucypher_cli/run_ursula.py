"""
!! WARNING !!
!! This is not an actual mining script: Don't use this to mine. !!

"""

import asyncio
import os

from cli.metadata import DEFAULT_SEED_NODE_DIR, collect_stored_nodes, write_node_metadata
from nucypher.characters import Ursula


def spin_up_ursula(seed_node_dir=DEFAULT_SEED_NODE_DIR, cleanup=True):

    # Collect nodes from the filesystem
    seed_nodes, other_nodes = collect_stored_nodes()

    # Start DHT loop
    asyncio.set_event_loop(asyncio.new_event_loop())

    # Initialize Ursula
    URSULA = Ursula.from_config(known_nodes=seed_nodes)
    URSULA.dht_listen()

    try:

        # Save node
        metadata_filepath = write_node_metadata(node=URSULA, node_metadata_dir=seed_node_dir)

        # Enter learning loop
        URSULA.start_learning_loop()
        URSULA.get_deployer().run()

    finally:

        if cleanup is True:
            os.remove(URSULA.db_name)
            os.remove(metadata_filepath)


if __name__ == "__main__":
    spin_up_ursula()
