import binascii
import os
from typing import Set

from nucypher.characters import Ursula
from nucypher.config.constants import DEFAULT_SEED_NODE_DIR


def read_node_metadata(filepath) -> Ursula:

    with open(filepath, "r") as seed_file:
        seed_file.seek(0)
        seed_node_bytes = binascii.unhexlify(seed_file.read())
        node = Ursula.from_bytes(seed_node_bytes, federated_only=True)
        return node


def write_node_metadata(node, node_metadata_dir: str) -> str:

    filename = "node-metadata-{}".format(node.rest_interface.port)
    metadata_filepath = os.path.join(node_metadata_dir, filename)

    with open(metadata_filepath, "w") as f:
        f.write(bytes(node).hex())

    return metadata_filepath


def read_metadata_dir(node_metadata_dir: str) -> Set[Ursula]:

    try:
        seed_node_files = os.listdir(node_metadata_dir)
    except FileNotFoundError:
        raise RuntimeError("No seed node metadata found at {}".format(node_metadata_dir))

    nodes = set()
    for seed_node_file in seed_node_files:
        node = read_node_metadata(filepath=seed_node_file)
        nodes.add(node)

    return nodes


def collect_stored_nodes(seed_node_dir=DEFAULT_SEED_NODE_DIR) -> tuple:
    """Collect stored node data from multiple sources and aggregate them into known node sets"""

    seed_nodes = read_metadata_dir(node_metadata_dir=seed_node_dir)
    other_nodes = set()
    return seed_nodes, other_nodes
