"""
!! WARNING !!
!! This is not an actual mining script: Don't use this to mine. !!

"""

import asyncio

from nucypher.characters import Ursula
from nucypher_cli.metadata import DEFAULT_SEED_NODE_DIR, collect_stored_nodes, write_node_metadata


def spin_up_ursula(seed_node_dir=DEFAULT_SEED_NODE_DIR):

    # Initialize #

    seed_nodes, other_nodes = collect_stored_nodes()     # Collect known nodes
    asyncio.set_event_loop(asyncio.new_event_loop())     # Init DHT async loop
    ursula = Ursula.from_config(known_nodes=seed_nodes)  # Init Ursula
    ursula.dht_listen()                                  # Start DHT

    # Execute #

    write_node_metadata(node=ursula,      # Save node
                        node_metadata_dir=seed_node_dir)

    ursula.start_learning_loop()          # Enter learning loop
    ursula.get_deployer().run()           # Run TLS Deployer


if __name__ == "__main__":
    spin_up_ursula()
