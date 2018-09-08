import configparser
import os
from shutil import copyfile
from typing import Tuple, Union

from nucypher.config.constants import (DEFAULT_CONFIG_ROOT,
                                       DEFAULT_INI_FILEPATH,
                                       DEFAULT_KEYRING_ROOT,
                                       DEFAULT_KNOWN_NODE_DIR,
                                       DEFAULT_SEED_NODE_DIR,
                                       DEFAULT_KNOWN_CERTIFICATES_DIR, DEFAULT_SEED_CERTIFICATES_DIR,
                                       DEFAULT_SEED_METADATA_DIR, DEFAULT_KNOWN_METADATA_DIR)


class NucypherConfigurationError(RuntimeError):
    pass


def initialize_configuration(config_root: str=None) -> None:
    """
    Create the configuration directory tree.
    If the directory already exists, FileExistsError is raised.
    """
    root = config_root if config_root else DEFAULT_CONFIG_ROOT

    # TODO: Check for existing config?

    #
    # Make configuration directories
    #

    os.mkdir(root, mode=0o755)                                   # config root
    os.mkdir(DEFAULT_KEYRING_ROOT, mode=0o700)                   # keyring

    os.mkdir(DEFAULT_KNOWN_NODE_DIR, mode=0o755)                 # known_nodes
    os.mkdir(DEFAULT_KNOWN_CERTIFICATES_DIR, mode=0o755)         # known_certs
    os.mkdir(DEFAULT_KNOWN_METADATA_DIR, mode=0o755)             # known_metadata

    os.mkdir(DEFAULT_SEED_NODE_DIR, mode=0o755)                  # seed_nodes
    os.mkdir(DEFAULT_SEED_CERTIFICATES_DIR, mode=0o755)          # seed_certs
    os.mkdir(DEFAULT_SEED_METADATA_DIR, mode=0o755)              # seed_metadata

    # Make a blank ini config file at the default path
    with open(DEFAULT_INI_FILEPATH, 'w+') as ini_file:
        if ini_file.read() == '':
            ini_file.seek(0)
            ini_file.write('[nucypher]')  # TODO Copy Default Sections, Perhaps interactively


def validate_passphrase(passphrase) -> bool:
    """Validate a passphrase and return True or raise an error with a failure reason"""

    rules = (
        (len(passphrase) >= 16, 'Passphrase is too short, must be >= 16 chars.'),
    )

    for rule, failure_message in rules:
        if not rule:
            raise NucypherConfigurationError(failure_message)
    return True


def check_config_tree(configuration_dir: str=None) -> bool:
    path = configuration_dir if configuration_dir else DEFAULT_CONFIG_ROOT
    if not os.path.exists(path):
        raise NucypherConfigurationError('No Nucypher configuration directory found at {}.'.format(configuration_dir))
    return True


def check_config_runtime() -> bool:
    rules = (
        (os.name == 'nt' or os.getuid() != 0, 'Cannot run as root user.'),
    )

    for rule, failure_reason in rules:
        if rule is not True:
            raise Exception(failure_reason)
    return True


def validate_nucypher_ini_config(config=None,
                                 filepath: str=DEFAULT_INI_FILEPATH,
                                 raise_on_failure: bool=False) -> Union[bool, Tuple[bool, tuple]]:

    if config is None:
        config = configparser.ConfigParser()
        config.read(filepath)

    if not config.sections():

        raise NucypherConfigurationError("Empty configuration file")

    required_sections = ("nucypher", "blockchain")

    missing_sections = list()

    try:
        operating_mode = config["nucypher"]["mode"]
    except KeyError:
        raise NucypherConfigurationError("No operating mode configured")
    else:
        modes = ('federated', 'testing', 'decentralized', 'centralized')
        if operating_mode not in modes:
            missing_sections.append("mode")
            if raise_on_failure is True:
                raise NucypherConfigurationError("Invalid nucypher operating mode '{}'. Specify {}".format(operating_mode, modes))

    for section in required_sections:
        if section not in config.sections():
            missing_sections.append(section)
            if raise_on_failure is True:
                raise NucypherConfigurationError("Invalid config file: missing section '{}'".format(section))

    if len(missing_sections) > 0:
        result = False, tuple(missing_sections)
    else:
        result = True, tuple()

    return result

