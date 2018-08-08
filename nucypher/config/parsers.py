import configparser

from web3 import IPCProvider

from nucypher.blockchain.eth.interfaces import EthereumContractRegistry, DeployerCircumflex, ControlCircumflex
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.blockchain.eth.utilities import TemporaryEthereumContractRegistry
from nucypher.config.constants import DEFAULT_INI_FILEPATH
from nucypher.config.utils import validate_nucypher_ini_config


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


def _parse_character_config(config=None, filepath: str=DEFAULT_INI_FILEPATH) -> dict:

    validate_nucypher_ini_config(filepath=filepath, config=config, raise_on_failure=True)

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


def _parse_ursula_config(config=None, federated_only=False, filepath: str=DEFAULT_INI_FILEPATH) -> dict:

    if config is None:
        config = configparser.ConfigParser()
        config.read(filepath)

    character_payload = _parse_character_config(config=config)

    ursula_payload = dict(  # Rest
                          rest_host=config.get(section='ursula.network.rest', option='host'),
                          rest_port=config.getint(section='ursula.network.rest', option='port'),
                          db_name=config.get(section='ursula.network.rest', option='db_name'),

                            # DHT
                          dht_host=config.get(section='ursula.network.dht', option='host'),
                          dht_port=config.getint(section='ursula.network.dht', option='port'))

    character_payload.update(ursula_payload)

    if not federated_only:
        address = config.get(section='ursula.blockchain', option='wallet_address')
        character_payload.update(dict(checksum_address=address))

    return character_payload


def parse_nucypher_ini_config(filepath: str=DEFAULT_INI_FILEPATH) -> dict:
    """Top-level parser with sub-parser routing"""

    validate_nucypher_ini_config(filepath=filepath, raise_on_failure=True)

    config = configparser.ConfigParser()
    config.read(filepath)

    # Parser router
    universal_parsers = {"character": _parse_character_config,
                         "ursula": _parse_ursula_config,
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
