import json
import os

from constant_sorrow.constants import NOT_RUNNING
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

    IPC_PROTOCOL = 'ipc'
    IPC_FILENAME = 'geth.ipc'
    VERBOSITY = 5

    _CHAIN_NAME = NotImplemented

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log = Logger('nucypher-geth')

    @property
    def provider_uri(self, scheme: str = None):
        if not scheme:
            scheme = self.IPC_PROTOCOL
        uri = f"{scheme}://{self.ipc_path}"
        return uri

    def start(self, timeout: int = 30):
        self.log.info("STARTING GETH NOW")
        super().start()
        self.wait_for_ipc(timeout=timeout)


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
            self.initialize_blockchain(geth_kwargs=geth_kwargs)

        self.__process = NOT_RUNNING

        super().__init__(geth_kwargs)

    @classmethod
    def initialize_blockchain(cls, geth_kwargs: dict) -> None:
        log = Logger('nucypher-geth-init')
        with open(cls.GENESIS_SOURCE_FILEPATH) as file:
            genesis_data = json.loads(file.read())
            log.info(f"Read genesis file '{cls.GENESIS_SOURCE_FILEPATH}'")

        log.info(f'Initializing new blockchain database and genesis block.')
        initialize_chain(genesis_data, **geth_kwargs)

    @classmethod
    def ensure_account_exists(cls, password: str, data_dir: str):
        geth_kwargs = {'network_id': str(cls.__CHAIN_ID),
                       'port': str(cls.P2P_PORT),
                       'verbosity': str(cls.VERBOSITY),
                       'data_dir': data_dir}

        accounts = get_accounts(**geth_kwargs)
        if not accounts:
            account = create_new_account(password=password.encode(), **geth_kwargs)
        else:
            account = accounts[0]
        return account
