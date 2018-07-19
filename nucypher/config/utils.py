import configparser
import os
from typing import Tuple

from web3 import IPCProvider

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


def validate_nucypher_ini_config(config=None,
                                 filepath: str=DEFAULT_INI_FILEPATH,
                                 raise_on_failure: bool=False) -> Tuple[bool, list]:

    if config is None:
        config = configparser.ConfigParser()

    try:
        config.read(filepath)
    except:
        raise  # FIXME

    required_sections = ("blockchain.provider", "nucypher")

    missing_sections = list()
    for section in required_sections:
        if section not in config.sections():
            missing_sections.append(section)
            if raise_on_failure is True:
                raise RuntimeError("Invalid config file: missing section '{}'".format(section))
    else:
        if len(missing_sections) > 0:
            return False, missing_sections


def parse_blockchain_config(config=None, filepath: str=DEFAULT_INI_FILEPATH) -> dict:
    from nucypher.blockchain.eth.chains import Blockchain, TesterBlockchain

    if config is None:
        config = configparser.ConfigParser()
        config.read(filepath)

    providers = list()
    if config['blockchain.provider']['type'] == 'ipc':
        try:
            provider = IPCProvider(config['blockchain.provider']['ipc_path'])
        except KeyError:
            message = "ipc_path must be provided when using an IPC provider"
            raise Exception(message)  # FIXME
        else:
            providers.append(provider)
    else:
        raise NotImplementedError

    poa = config.getboolean(section='blockchain.provider', option='poa', fallback=True)
    tester = config.getboolean(section='blockchain', option='tester', fallback=False)
    test_accounts = config.getint(section='blockchain', option='test_accounts', fallback=0)
    deploy = config.getboolean(section='blockchain', option='deploy', fallback=False)
    compile = config.getboolean(section='blockchain', option='compile', fallback=False)
    timeout = config.getint(section='blockchain', option='timeout', fallback=10)
    tmp_registry = config.getboolean(section='blockchain', option='temporary_registry', fallback=False)
    registry_filepath = config.get(section='blockchain', option='registry_filepath', fallback='.registry.json')

    #
    # Initialize
    #

    compiler = SolidityCompiler() if compile else None

    if tmp_registry:
        registry = TemporaryEthereumContractRegistry()
    else:
        registry = EthereumContractRegistry(registry_filepath=registry_filepath)

    interface_class = ControlCircumflex if not deploy else DeployerCircumflex
    circumflex = interface_class(timeout=timeout,
                                 providers=providers,
                                 compiler=compiler,
                                 registry=registry)

    if tester:
        blockchain = TesterBlockchain(interface=circumflex,
                                      poa=poa,
                                      test_accounts=test_accounts,
                                      airdrop=True)
    else:
        blockchain = Blockchain(interface=circumflex)

    blockchain_payload = dict(compiler=compiler,
                              registry=registry,
                              interface=circumflex,
                              blockchain=blockchain,
                              tester=tester,
                              test_accounts=test_accounts,
                              deploy=deploy,
                              poa=poa,
                              timeout=timeout,
                              tmp_registry=tmp_registry,
                              registry_filepath=registry_filepath)

    return blockchain_payload


def _parse_character_config(config=None, filepath: str=DEFAULT_INI_FILEPATH):

    if config is None:
        config = configparser.ConfigParser()
        config.read(filepath)

    character_payload = dict(start_learning_on_same_thread=config.getboolean(section='character', option='start_learning_on_same_thread'),
                             abort_on_learning_error=config.getboolean(section='character', option='abort_on_learning_error'),
                             federated_only=config.getboolean(section='character', option='federated'),
                             checksum_address=config.get(section='character', option='ethereum_address'),
                             always_be_learning=config.getboolean(section='character', option='always_be_learning'))

    return character_payload


def _parse_ursula_config(config=None, filepath: str=DEFAULT_INI_FILEPATH):

    if config is None:
        config = configparser.ConfigParser()
        config.read(filepath)

    if "stake" in config.sections():

        try:
            stake_index = int(config["ursula"]["stake"])
        except ValueError:
            stakes = []
            stake_index_tags = {'latest': len(stakes),
                                'only': stakes[0]}

            raise NotImplementedError

    ursula_payload = dict(checksum_address=config.get(section='ursula', option='wallet_address'),

                          # Rest
                          rest_host=config.get(section='ursula.network.rest', option='host'),
                          rest_port=config.getint(section='ursula.network.rest', option='port'),
                          db_name=config.get(section='ursula.network.rest', option='db_name'),

                          # DHT
                          dht_host=config.get(section='ursula.network.dht', option='host'),
                          dht_port=config.getint(section='ursula.network.dht', option='port'))

    return ursula_payload


def parse_nucypher_ini_config(filepath: str=DEFAULT_INI_FILEPATH) -> dict:
    """Top-level parser with sub-parser routing"""

    validate_nucypher_ini_config(filepath=filepath, raise_on_failure=True)

    config = configparser.ConfigParser()
    config.read(filepath)

    # Parser router
    parsers = {"character": _parse_character_config,
               "blockchain": parse_blockchain_config,
               "ursula": _parse_ursula_config,
               }

    staged_payloads = list()
    for section, parser in parsers.items():
        section_payload = parser(config)
        staged_payloads.append(section_payload)

    payload = dict()
    for staged_payload in staged_payloads:
        payload.update(staged_payload)

    return payload
