import os

from nkms.config.keys import KMSKeyring
from .configs import _DEFAULT_CONFIGURATION_DIR


def generate_confg_dir(path: str=None,) -> None:
    """
    Create the configuration directory tree.
    If the directory already exists, FileExistsError is raised.
    """
    path = path if path else _DEFAULT_CONFIGURATION_DIR

    if not os.path.exists(path):
        os.mkdir(path, mode=0o755)


def check_config_tree(configuration_dir: str=None) -> bool:
    path = configuration_dir if configuration_dir else _DEFAULT_CONFIGURATION_DIR
    if not os.path.exists(path):
        raise FileNotFoundError('No KMS configuration directory found at {}.'.format(configuration_dir))
    return True


def check_config_runtime() -> bool:
    rules = (
        (os.getuid() != 0, 'Cannot run as root user.'),

    )

    for rule, failure_reason in rules:
        if rule is not True:
            raise Exception(failure_reason)
    return True


def _bootstrap_config():
    """Do not actually use this."""
    passphrase = input("Enter passphrase >> ")
    return KMSKeyring.generate(passphrase=passphrase)

