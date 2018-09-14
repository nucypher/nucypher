import binascii
import os
from glob import glob
from os.path import abspath

from nucypher.characters import Ursula
from nucypher.config.constants import DEFAULT_SEED_NODE_DIR, DEFAULT_KNOWN_NODE_DIR, DEFAULT_CONFIG_ROOT


def read_node_metadata(filepath: str, federated_only=False) -> Ursula:

    """Init one ursula from node storage file"""

    with open(filepath, "r") as seed_file:
        seed_file.seek(0)
        node_bytes = binascii.unhexlify(seed_file.read())

        node = Ursula.from_bytes(node_bytes, federated_only=federated_only)
        return node


def write_node_metadata(node: Ursula,
                        seed_node: bool = False,
                        node_metadata_dir: str = DEFAULT_KNOWN_NODE_DIR) -> str:

    try:
        filename = "node-metadata-{}".format(node.rest_interface.port)
    except AttributeError:
        raise AttributeError("{} does not have a rest_interface attached".format(node))

    node_type = 'known' if not seed_node else 'seed'
    metadata_filepath = os.path.join(node_metadata_dir, '{}_nodes'.format(node_type), filename)

    with open(metadata_filepath, "w") as f:
        f.write(bytes(node).hex())

    return metadata_filepath


def collect_stored_nodes(config_root=DEFAULT_CONFIG_ROOT,
                         seed_nodes_dirs=None,
                         known_nodes_dirs: list=None,
                         federated_only=False) -> tuple:
    """Collect stored node data from multiple sources and aggregate them into known node sets"""

    if known_nodes_dirs is None:
        known_nodes_dirs = [DEFAULT_KNOWN_NODE_DIR]

    if seed_nodes_dirs is None:
        seed_nodes_dirs = [DEFAULT_SEED_NODE_DIR]

    # TODO: use seed bucket?
    _all_node_dirs = known_nodes_dirs + seed_nodes_dirs

    glob_pattern = os.path.join(config_root, '*', 'node-metadata-*',)
    metadata_paths = sorted(glob(glob_pattern), key=os.path.getctime)

    nodes = list()
    for metadata_path in metadata_paths:
        node = read_node_metadata(filepath=abspath(metadata_path), federated_only=federated_only)
        nodes.append(node)

    return tuple(nodes)
