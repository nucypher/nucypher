import json
import os

from geth import LoggingMixin
from geth.accounts import ensure_account_exists
from geth.chain import get_chain_data_dir, initialize_chain, is_live_chain, \
    is_ropsten_chain
from geth.process import BaseGethProcess
from twisted.logger import Logger

from nucypher.config.constants import DEFAULT_CONFIG_ROOT


NUCYPHER_CHAIN_IDS = {
    'devnet': 112358,
}


class NuCypherGethProcess(BaseGethProcess, LoggingMixin):

    GENESIS_FILENAME = 'genesis.json'
    GENESIS_SOURCE_FILEPATH = os.path.join('deploy', 'geth', GENESIS_FILENAME)
    IPC_FILENAME = 'geth.ipc'
    VERBOSITY = 5

    _CHAIN_NAME = NotImplemented

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log = Logger('nucypher-geth')

    def start(self):
        self.log.info("STARTING GETH NOW")
        super().start()

    def initialize_blockchain(self, geth_kwargs: dict) -> None:
        with open(self.GENESIS_SOURCE_FILEPATH) as file:
            genesis_data = json.loads(file.read())
            self.log.info(f"Read genesis file '{self.GENESIS_SOURCE_FILEPATH}'")

        self.log.info(f'Initializing new blockchain database and genesis block.')
        initialize_chain(genesis_data, **geth_kwargs)


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

        _coinbase = ensure_account_exists(**geth_kwargs)

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

        super().__init__(geth_kwargs)
