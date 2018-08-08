import asyncio

import click

from nucypher.characters import Ursula
from nucypher_cli.metadata import collect_stored_nodes, write_node_metadata

RUNTIME_DIR = './.nucypher'




if __name__ == "__main__":
    run_ursula()
