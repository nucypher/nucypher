import json
import os

import click
from geth import LoggingMixin
from geth.accounts import ensure_account_exists
from geth.chain import get_chain_data_dir, initialize_chain, is_live_chain, \
    is_ropsten_chain
from geth.process import BaseGethProcess
from geth.wrapper import construct_test_chain_kwargs

from nucypher.config.constants import DEFAULT_CONFIG_ROOT


NUCYPHER_CHAIN_IDS = {
    'devnet': 112358,
}


class NuCypherGethDevProcess(BaseGethProcess, LoggingMixin):

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


class NuCypherGethDevnetProcess(LoggingMixin, BaseGethProcess):

    GENESIS_FILEPATH = os.path.join('deploy', 'geth', 'genesis.json')
    __CHAIN_NAME = 'devnet'
    __CHAIN_ID = NUCYPHER_CHAIN_IDS[__CHAIN_NAME]

    def __init__(self,
                 password: str = None,
                 config_root: str = None,
                 overrides: dict = None):

        # if password is None:
        #     password = click.prompt("Enter Geth node password: ", hide_input=True)

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
        self.data_dir = get_chain_data_dir(base_dir=base_dir, name=self.__CHAIN_NAME)

        # Hardcoded Geth CLI args for devnet child process
        ipc_path = os.path.join(self.data_dir, 'geth.ipc')
        geth_kwargs = {'unlock': '0',
                       'network_id': str(self.__CHAIN_ID),
                       'port': '30303',
                       'verbosity': '5',
                       'rpc_enabled': 'true',
                       'data_dir': self.data_dir,
                       'ipc_path': ipc_path}

        _coinbase = ensure_account_exists(**geth_kwargs)

        # Genesis & Blockchain Init
        genesis_filepath = self.GENESIS_FILEPATH
        needs_init = all((
            not os.path.exists(genesis_filepath),
            not is_live_chain(self.data_dir),
            not is_ropsten_chain(self.data_dir),
        ))

        if needs_init:
            with open(genesis_filepath) as file:
                genesis_data = json.loads(file.read())
            initialize_chain(genesis_data, **geth_kwargs)

        super().__init__(geth_kwargs)
