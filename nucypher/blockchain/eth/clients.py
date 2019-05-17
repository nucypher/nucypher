import json
import os
import shutil
import time
from abc import ABC, abstractmethod

from constant_sorrow.constants import NOT_RUNNING
from eth_utils import to_checksum_address, is_checksum_address
from geth import LoggingMixin
from geth.accounts import get_accounts, create_new_account
from geth.chain import (
    get_chain_data_dir,
    initialize_chain,
    is_live_chain,
    is_ropsten_chain
)
from geth.process import BaseGethProcess
from twisted.logger import Logger
from web3 import Web3

from nucypher.config.constants import DEFAULT_CONFIG_ROOT, DEPLOY_DIR, USER_LOG_DIR

NUCYPHER_CHAIN_IDS = {
    'devnet': 112358,
}


class Web3ClientError(Exception):
    pass


class Web3ClientConnectionFailed(Web3ClientError):
    pass


class Web3ClientUnexpectedVersionString(Web3ClientError):
    pass


class BaseWeb3ClientAPIHelper(ABC):
    def __init__(self, w3: Web3):
        self.web3_instance = w3

    @property
    def client_version(self) -> str:
        return self.web3_instance.clientVersion

    @property
    @abstractmethod
    def node_technology(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def node_version(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def platform(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def backend(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def peers(self):
        raise NotImplementedError

    @property
    def syncing(self):
        return self.web3_instance.eth.syncing

    @abstractmethod
    def unlock_account(self, address, password):
        raise NotImplementedError


class GethBaseWeb3ClientAPIHelper(BaseWeb3ClientAPIHelper):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        client_version = self.client_version
        node_info = client_version.split('/')
        if len(node_info) != 4:
            raise Web3ClientUnexpectedVersionString(f'Unexpected Geth client version string '
                                                    f'received {client_version}')
        self.node_technology, self.node_version, self.platform, self.backend = node_info

    def node_technology(self) -> str:
        return self.node_technology

    def node_version(self) -> str:
        return self.node_version

    def platform(self) -> str:
        return self.platform

    def backend(self) -> str:
        return self.backend

    @property
    def peers(self):
        return self.web3_instance.geth.admin.peers()

    def unlock_account(self, address, password):
        return self.web3_instance.geth.personal.unlockAccount(address, password)


class ParityBaseWeb3ClientAPIHelper(BaseWeb3ClientAPIHelper):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        client_version = self.client_version
        node_info = client_version.split('/')
        if len(node_info) != 4:
            raise Web3ClientUnexpectedVersionString(f'Unexpected Parity client version string '
                                                    f'received {client_version}')
        self.node_technology, self.node_version, self.platform, self.backend = node_info

    def node_technology(self) -> str:
        return self.node_technology

    def node_version(self) -> str:
        return self.node_version

    def platform(self) -> str:
        return self.platform()

    def backend(self) -> str:
        return self.backend

    def peers(self) -> str:
        return self.web3_instance.manager.request_blocking("parity_netPeers", [])

    def unlock_account(self, address, password):
        return self.web3_instance.parity.unlockAccount.unlockAccount(address, password)


class GanacheBaseWeb3ClientAPIHelper(BaseWeb3ClientAPIHelper):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        client_version = self.client_version
        node_info = client_version.split('/')
        if len(node_info) != 3:
            raise Web3ClientUnexpectedVersionString(f'Unexpected Ganache client version string '
                                                    f'received {client_version}')
        self.node_technology, self.node_version, self.backend = node_info

    def node_technology(self) -> str:
        return self.node_technology

    def node_version(self) -> str:
        return self.node_version

    def platform(self) -> str:
        raise NotImplementedError('Ganache client does not provide a result for platform')

    def backend(self) -> str:
        return self.backend

    def peers(self):
        raise NotImplementedError('Ganache has no (documented) endpoint for peers')

    def unlock_account(self, address, password):
        raise NotImplementedError("Ganache has a JSONRPC endpoint 'personal_unlockAccount' that we "
                                  "haven't implemented yet")


class Web3Client:
    GETH = 'Geth'
    PARITY = 'Parity'
    GANACHE = 'EthereumJS TestRPC'

    def __init__(self,
                 w3: Web3):
        self.web3_instance = w3

        if not self.web3_instance.isConnected():
            raise Web3ClientConnectionFailed(f'Failed to connect to provider: {self._web3_instance.provider}')
        self.web3_api_helper = self.determine_web3_api_helper()

    def determine_web3_api_helper(self) -> BaseWeb3ClientAPIHelper:
        #
        # *Client version format*
        # Geth Example: "'Geth/v1.4.11-stable-fed692f6/darwin/go1.7'"
        # Parity Example: "Parity//v1.5.0-unstable-9db3f38-20170103/x86_64-linux-gnu/rustc1.14.0"
        # Ganache Example: "EthereumJS TestRPC/v2.1.5/ethereum-js"
        #
        client_version = self.web3_instance.clientVersion
        node_info = client_version.split('/')
        node_technology = node_info[0]
        if node_technology == Web3Client.GETH:
            return GethBaseWeb3ClientAPIHelper(self.web3_instance)
        elif node_technology == Web3Client.PARITY:
            return ParityBaseWeb3ClientAPIHelper(self.web3_instance)
        elif node_technology == Web3Client.GANACHE:
            return GanacheBaseWeb3ClientAPIHelper(self.web3_instance)
        else:
            raise NotImplemented

    @property
    def is_connected(self) -> bool:
        return self.web3_instance.isConnected()

    @property
    def node_technology(self) -> str:
        return self.web3_api_helper.node_technology

    @property
    def node_version(self) -> str:
        return self.web3_api_helper.node_version

    @property
    def platform(self) -> str:
        return self.web3_api_helper.platform

    @property
    def backend(self) -> str:
        return self.web3_api_helper.backend

    @property
    def peers(self):
        return self.web3_api_helper.peers

    @property
    def syncing(self):
        return self.web3_api_helper.syncing

    def unlock_account(self, address, password):
        return self.web3_api_helper.unlock_account(address, password)


class NuCypherGethProcess(LoggingMixin, BaseGethProcess):
    IPC_PROTOCOL = 'http'
    IPC_FILENAME = 'geth.ipc'
    VERBOSITY = 5
    LOG_PATH = os.path.join(USER_LOG_DIR, 'nucypher-geth.log')

    _CHAIN_NAME = NotImplemented

    def __init__(self,
                 geth_kwargs: dict,
                 stdout_logfile_path: str = LOG_PATH,
                 stderr_logfile_path: str = LOG_PATH,
                 *args, **kwargs):

        super().__init__(geth_kwargs=geth_kwargs,
                         stdout_logfile_path=stdout_logfile_path,
                         stderr_logfile_path=stderr_logfile_path,
                         *args, **kwargs)

        self.log = Logger('nucypher-geth')

    @property
    def provider_uri(self, scheme: str = None) -> str:
        if not scheme:
            scheme = self.IPC_PROTOCOL
        if scheme == 'file':
            location = self.ipc_path
        elif scheme in ('http', 'ws'):
            location = f'{self.rpc_host}:{self.rpc_port}'
        else:
            raise ValueError(f'{scheme} is an unknown ethereum node IPC protocol.')

        uri = f"{scheme}://{location}"
        return uri

    def start(self, timeout: int = 30, extra_delay: int = 1):
        self.log.info("STARTING GETH NOW")
        super().start()
        self.wait_for_ipc(timeout=timeout)  # on for all nodes by default
        if self.IPC_PROTOCOL in ('rpc', 'http'):
            self.wait_for_rpc(timeout=timeout)
        time.sleep(extra_delay)


class NuCypherGethDevProcess(NuCypherGethProcess):

    _CHAIN_NAME = 'poa-development'

    def __init__(self, config_root: str = None, *args, **kwargs):

        base_dir = config_root if config_root else DEFAULT_CONFIG_ROOT
        base_dir = os.path.join(base_dir, '.ethereum')
        self.data_dir = get_chain_data_dir(base_dir=base_dir, name=self._CHAIN_NAME)

        ipc_path = os.path.join(self.data_dir, 'geth.ipc')
        self.geth_kwargs = {'ipc_path': ipc_path}
        super().__init__(geth_kwargs=self.geth_kwargs, *args, **kwargs)
        self.geth_kwargs.update({'dev': True})

        self.command = [*self.command, '--dev']


class NuCypherGethDevnetProcess(NuCypherGethProcess):

    IPC_PROTOCOL = 'file'
    GENESIS_FILENAME = 'testnet_genesis.json'
    GENESIS_SOURCE_FILEPATH = os.path.join(DEPLOY_DIR, GENESIS_FILENAME)

    P2P_PORT = 30303
    _CHAIN_NAME = 'devnet'
    __CHAIN_ID = NUCYPHER_CHAIN_IDS[_CHAIN_NAME]

    def __init__(self,
                 config_root: str = None,
                 overrides: dict = None,
                 *args, **kwargs):

        log = Logger('nucypher-geth-devnet')

        if overrides is None:
            overrides = dict()

        # Validate
        invalid_override = f"You cannot specify `network_id` for a {self.__class__.__name__}"
        if 'data_dir' in overrides:
            raise ValueError(invalid_override)
        if 'network_id' in overrides:
            raise ValueError(invalid_override)

        # Set the data dir
        if config_root is None:
            base_dir = os.path.join(DEFAULT_CONFIG_ROOT, '.ethereum')
        else:
            base_dir = os.path.join(config_root, '.ethereum')
        self.data_dir = get_chain_data_dir(base_dir=base_dir, name=self._CHAIN_NAME)

        # Hardcoded Geth CLI args for devnet child process ("light client")
        ipc_path = os.path.join(self.data_dir, self.IPC_FILENAME)
        geth_kwargs = {'network_id': str(self.__CHAIN_ID),
                       'port': str(self.P2P_PORT),
                       'verbosity': str(self.VERBOSITY),
                       'data_dir': self.data_dir,
                       'ipc_path': ipc_path,
                       'rpc_enabled': True,
                       'no_discover': True,
                       }

        # Genesis & Blockchain Init
        self.genesis_filepath = os.path.join(self.data_dir, self.GENESIS_FILENAME)
        needs_init = all((
            not os.path.exists(self.genesis_filepath),
            not is_live_chain(self.data_dir),
            not is_ropsten_chain(self.data_dir),
        ))

        if needs_init:
            log.debug("Local system needs geth blockchain initialization")
            self.initialized = False
        else:
            self.initialized = True

        self.__process = NOT_RUNNING
        super().__init__(geth_kwargs=geth_kwargs, *args, **kwargs)  # Attaches self.geth_kwargs in super call
        self.command = [*self.command, '--syncmode', 'fast']

    def get_accounts(self):
        accounts = get_accounts(**self.geth_kwargs)
        return accounts

    def initialize_blockchain(self, overwrite: bool = True) -> None:
        log = Logger('nucypher-geth-init')
        with open(self.GENESIS_SOURCE_FILEPATH, 'r') as file:
            genesis_data = json.loads(file.read())
            log.info(f"Read genesis file '{self.GENESIS_SOURCE_FILEPATH}'")

        genesis_data.update(dict(overwrite=overwrite))
        log.info(f'Initializing new blockchain database and genesis block.')
        initialize_chain(genesis_data=genesis_data, **self.geth_kwargs)

        # Write static nodes file to data dir
        bootnodes_filepath = os.path.join(DEPLOY_DIR, 'static-nodes.json')
        shutil.copy(bootnodes_filepath, os.path.join(self.data_dir))

    def ensure_account_exists(self, password: str) -> str:
        accounts = get_accounts(**self.geth_kwargs)
        if not accounts:
            account = create_new_account(password=password.encode(), **self.geth_kwargs)
        else:
            account = accounts[0]

        checksum_address = to_checksum_address(account.decode())
        assert is_checksum_address(checksum_address), f"GETH RETURNED INVALID ETH ADDRESS {checksum_address}"
        return checksum_address

    def start(self, *args, **kwargs):
        # FIXME: Quick and Dirty

        # Write static nodes file to data dir
        bootnodes_filepath = os.path.join(DEPLOY_DIR, 'static-nodes.json')
        shutil.copy(bootnodes_filepath, os.path.join(self.data_dir))
        super().start()
