import json
import os

from constant_sorrow.constants import NOT_RUNNING
from eth_utils import to_checksum_address, is_checksum_address
from geth import LoggingMixin
from geth.accounts import ensure_account_exists, get_accounts, create_new_account
from geth.chain import (
    get_chain_data_dir,
    initialize_chain,
    is_live_chain,
    is_ropsten_chain
)
from geth.process import BaseGethProcess
from twisted.logger import Logger

from nucypher.config.constants import DEFAULT_CONFIG_ROOT, BASE_DIR, DEPLOY_DIR

NUCYPHER_CHAIN_IDS = {
    'devnet': 112358,
}


class NuCypherGethProcess(BaseGethProcess, LoggingMixin):

    IPC_PROTOCOL = 'http'
    IPC_FILENAME = 'geth.ipc'
    VERBOSITY = 5

    _CHAIN_NAME = NotImplemented

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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

    def start(self, timeout: int = 30):
        self.log.info("STARTING GETH NOW")
        super().start()
        self.wait_for_ipc(timeout=timeout)  # on for all nodes by default
        if self.IPC_PROTOCOL == 'rpc':
            self.wait_for_rpc(timeout=timeout)


class NuCypherGethDevProcess(NuCypherGethProcess):

    _CHAIN_NAME = 'poa-development'

    def __init__(self, config_root: str = None):

        base_dir = config_root if config_root else DEFAULT_CONFIG_ROOT
        base_dir = os.path.join(base_dir, '.ethereum')
        self.data_dir = get_chain_data_dir(base_dir=base_dir, name=self._CHAIN_NAME)

        ipc_path = os.path.join(self.data_dir, 'geth.ipc')
        self.geth_kwargs = {'ipc_path': ipc_path}
        super().__init__(geth_kwargs=self.geth_kwargs)
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
                 overrides: dict = None):

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
                       'ipc_path': ipc_path}

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
        super().__init__(geth_kwargs)  # Attaches self.geth_kwargs in super call

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

    def ensure_account_exists(self, password: str) -> str:
        accounts = get_accounts(**self.geth_kwargs)
        if not accounts:
            account = create_new_account(password=password.encode(), **self.geth_kwargs)
        else:
            account = accounts[0]

        checksum_address = to_checksum_address(account.decode())
        assert is_checksum_address(checksum_address), f"GETH RETURNED INVALID ETH ADDRESS {checksum_address}"
        return checksum_address
