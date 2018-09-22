"""
Parse configuration files into dictionaries and return them for consumption by constructors.
"""

import configparser

from constant_sorrow import constants

from nucypher.config.constants import DEFAULT_CONFIG_FILE_LOCATION
from nucypher.config.utils import validate_configuration_file


def parse_blockchain_config(config=None, filepath: str=DEFAULT_CONFIG_FILE_LOCATION) -> dict:
    """Parse blockchain configuration data"""

    if config is None:
        config = configparser.ConfigParser()
        config.read(filepath)

    simulation = config.getboolean(section='nucypher', option='simulation', fallback=False)
    compile = config.getboolean(section='blockchain', option='compile', fallback=False)

    provider_uri = config.get(section='blockchain', option='provider_uri')
    timeout = config.getint(section='blockchain', option='timeout', fallback=10)

    deploy = config.getboolean(section='blockchain', option='deploy', fallback=False)
    tester = config.getboolean(section='blockchain', option='tester', fallback=False)
    poa = config.getboolean(section='blockchain', option='poa', fallback=True)
    test_accounts = config.getint(section='blockchain', option='test_accounts', fallback=0)

    tmp_registry = config.getboolean(section='blockchain', option='temporary_registry', fallback=False)
    registry_filepath = config.get(section='blockchain', option='registry_filepath', fallback='.registry.json')

    blockchain_payload = dict(compile=compile,
                              simulation=simulation,
                              tester=tester,
                              test_accounts=test_accounts,
                              provider_uri=provider_uri,
                              deploy=deploy,
                              poa=poa,
                              timeout=timeout,
                              tmp_registry=tmp_registry,
                              registry_filepath=registry_filepath)

    return blockchain_payload


def parse_character_config(config=None, filepath: str=DEFAULT_CONFIG_FILE_LOCATION) -> dict:
    """Parse non character-specific configuration data"""

    if config is None:
        config = configparser.ConfigParser()
        config.read(filepath)

    validate_configuration_file(filepath=filepath, config=config, raise_on_failure=True)

    operating_mode = config["nucypher"]["mode"]
    if operating_mode == "federated":
        federated_only = True
    else:
        federated_only = False

    character_payload = dict(federated_only=federated_only,
                             start_learning_on_same_thread=config.getboolean(section='character', option='start_learning_on_same_thread'),
                             abort_on_learning_error=config.getboolean(section='character', option='abort_on_learning_error'),
                             always_be_learning=config.getboolean(section='character', option='always_be_learning'))

    return character_payload


def parse_ursula_config(config=None, filepath: str=DEFAULT_CONFIG_FILE_LOCATION) -> dict:
    """Parse Ursula-specific configuration data"""

    if config is None:
        config = configparser.ConfigParser()
        config.read(filepath)

    character_payload = parse_character_config(config=config)

    ursula_payload = dict(  # Rest
                          rest_host=config.get(section='ursula.network.rest', option='host'),
                          rest_port=config.getint(section='ursula.network.rest', option='port'),
                          db_name=config.get(section='ursula.network.rest', option='db_name'),
                          )

    character_payload.update(ursula_payload)

    if not character_payload['federated_only']:
        address = config.get(section='ursula.blockchain', option='wallet_address', fallback=constants.NO_ADDRESS_CONFIGURED)
        character_payload.update(dict(checksum_address=address))

    return character_payload


def parse_alice_config(config=None, filepath=DEFAULT_CONFIG_FILE_LOCATION) -> dict:

    if config is None:
        config = configparser.ConfigParser()
        config.read(filepath)

    character_payload = parse_character_config(config=config)

    alice_payload = dict()  # type: dict # Alice specific

    character_payload.update(alice_payload)

    return character_payload


def parse_running_modes(filepath: str=DEFAULT_CONFIG_FILE_LOCATION) -> dict:
    """Parse high-level operating and control modes"""

    # validate_nucypher_ini_config(filepath=filepath, raise_on_failure=True)

    config = configparser.ConfigParser()
    config.read(filepath)

    operating_mode = config.get(section='nucypher', option='mode')
    simulation_mode = config.getboolean(section='nucypher', option='simulation', fallback=False)

    mode_payload = dict(operating_mode=operating_mode, simulation=simulation_mode)
    return mode_payload


def parse_configuration_file(filepath: str=DEFAULT_CONFIG_FILE_LOCATION) -> dict:
    """Top-level parser with sub-parser routing"""

    validate_configuration_file(filepath=filepath, raise_on_failure=True)

    config = configparser.ConfigParser()
    config.read(filepath)

    # Parser router
    universal_parsers = {"character": parse_character_config,
                         "ursula": parse_ursula_config,
                         }

    operating_mode = config["nucypher"]["mode"]
    if operating_mode == "decentralized":
        decentralized_parsers = {"blockchain": parse_blockchain_config, }
        universal_parsers.update(decentralized_parsers)
    parsers = universal_parsers

    staged_payloads = list()
    for section, parser in parsers.items():
        section_payload = parser(config)
        staged_payloads.append(section_payload)

    payload = {'operating_mode': operating_mode}
    for staged_payload in staged_payloads:
        payload.update(staged_payload)

    return payload
