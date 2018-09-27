import configparser
import os
from typing import Union, Tuple

from nucypher.config.constants import DEFAULT_CONFIG_FILE_LOCATION
from nucypher.config.node import NodeConfiguration


def validate_passphrase(passphrase) -> bool:
    """Validate a passphrase and return True or raise an error with a failure reason"""

    rules = (
        (len(passphrase) >= 16, 'Passphrase is too short, must be >= 16 chars.'),
    )

    for rule, failure_message in rules:
        if not rule:
            raise NodeConfiguration.ConfigurationError(failure_message)
    return True


def check_config_permissions() -> bool:
    rules = (
        (os.name == 'nt' or os.getuid() != 0, 'Cannot run as root user.'),
    )

    for rule, failure_reason in rules:
        if rule is not True:
            raise Exception(failure_reason)
    return True


def validate_configuration_file(config=None,
                                filepath: str = DEFAULT_CONFIG_FILE_LOCATION,
                                raise_on_failure: bool=False) -> Union[bool, Tuple[bool, tuple]]:

    if config is None:
        config = configparser.ConfigParser()
        config.read(filepath)

    if not config.sections():

        raise NodeConfiguration.InvalidConfiguration("Empty configuration file")

    required_sections = ("nucypher", "blockchain")

    missing_sections = list()

    try:
        operating_mode = config["nucypher"]["mode"]
    except KeyError:
        raise NodeConfiguration.ConfigurationError("No operating mode configured")
    else:
        modes = ('federated', 'testing', 'decentralized', 'centralized')
        if operating_mode not in modes:
            missing_sections.append("mode")
            if raise_on_failure is True:
                raise NodeConfiguration.ConfigurationError("Invalid nucypher operating mode '{}'. Specify {}".format(operating_mode, modes))

    for section in required_sections:
        if section not in config.sections():
            missing_sections.append(section)
            if raise_on_failure is True:
                raise NodeConfiguration.ConfigurationError("Invalid config file: missing section '{}'".format(section))

    if len(missing_sections) > 0:
        result = False, tuple(missing_sections)
    else:
        result = True, tuple()

    return result
