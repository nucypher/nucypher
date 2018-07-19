import configparser
import os
from typing import Tuple

from web3 import IPCProvider

from nucypher.blockchain.eth.chains import Blockchain, TesterBlockchain
from nucypher.blockchain.eth.interfaces import EthereumContractRegistry, DeployerCircumflex, ControlCircumflex
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.blockchain.eth.utilities import TemporaryEthereumContractRegistry


DEFAULT_CONFIG_DIR = "~"
DEFAULT_INI_FILEPATH = './.nucypher.ini'


def generate_confg_dir(path: str=None,) -> None:
    """
    Create the configuration directory tree.
    If the directory already exists, FileExistsError is raised.
    """
    path = path if path else DEFAULT_CONFIG_DIR
    if not os.path.exists(path):
        os.mkdir(path, mode=0o755)


def validate_passphrase(passphrase) -> bool:
    """Validate a passphrase and return True or raise an error with a failure reason"""

    rules = (
        (len(passphrase) >= 16, 'Passphrase is too short, must be >= 16 chars.'),
    )

    for rule, failure_message in rules:
        if not rule:
            raise RuntimeError(failure_message)
    return True


def check_config_tree(configuration_dir: str=None) -> bool:
    path = configuration_dir if configuration_dir else DEFAULT_CONFIG_DIR
    if not os.path.exists(path):
        raise FileNotFoundError('No NuCypher configuration directory found at {}.'.format(configuration_dir))
    return True


def check_config_runtime() -> bool:
    rules = (
        (os.name == 'nt' or os.getuid() != 0, 'Cannot run as root user.'),
    )

    for rule, failure_reason in rules:
        if rule is not True:
            raise Exception(failure_reason)
    return True


