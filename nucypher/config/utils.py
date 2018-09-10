import configparser
import os
from glob import glob
from os.path import abspath
from typing import Union, Tuple

from nucypher.config.config import NodeConfiguration


def collect_stored_nodes(known_metadata_dir=None) -> set:

    nodes = set()
    glob_pattern = os.path.join(known_metadata_dir, 'node-metadata-*')
    metadata_paths = sorted(glob(glob_pattern), key=os.path.getctime)

    for metadata_path in metadata_paths:
        from nucypher.characters import Ursula
        node = Ursula.from_metadata_file(filepath=abspath(metadata_path))
        nodes.add(node)

    return nodes


def validate_passphrase(passphrase) -> bool:
    """Validate a passphrase and return True or raise an error with a failure reason"""

    rules = (
        (len(passphrase) >= 16, 'Passphrase is too short, must be >= 16 chars.'),
    )

    for rule, failure_message in rules:
        if not rule:
            raise NodeConfiguration.NucypherConfigurationError(failure_message)
    return True


def check_config_permissions() -> bool:
    rules = (
        (os.name == 'nt' or os.getuid() != 0, 'Cannot run as root user.'),
    )

    for rule, failure_reason in rules:
        if rule is not True:
            raise Exception(failure_reason)
    return True


def validate_nucypher_ini_config(config=None,
                                 filepath: str = NodeConfiguration.DEFAULT_INI_FILEPATH,
                                 raise_on_failure: bool=False) -> Union[bool, Tuple[bool, tuple]]:

    if config is None:
        config = configparser.ConfigParser()
        config.read(filepath)

    if not config.sections():

        raise NodeConfiguration.NucypherConfigurationError("Empty configuration file")

    required_sections = ("nucypher", "blockchain")

    missing_sections = list()

    try:
        operating_mode = config["nucypher"]["mode"]
    except KeyError:
        raise NodeConfiguration.NucypherConfigurationError("No operating mode configured")
    else:
        modes = ('federated', 'testing', 'decentralized', 'centralized')
        if operating_mode not in modes:
            missing_sections.append("mode")
            if raise_on_failure is True:
                raise NodeConfiguration.NucypherConfigurationError("Invalid nucypher operating mode '{}'. Specify {}".format(operating_mode, modes))

    for section in required_sections:
        if section not in config.sections():
            missing_sections.append(section)
            if raise_on_failure is True:
                raise NodeConfiguration.NucypherConfigurationError("Invalid config file: missing section '{}'".format(section))

    if len(missing_sections) > 0:
        result = False, tuple(missing_sections)
    else:
        result = True, tuple()

    return result
