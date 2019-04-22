import os
import shutil

from geth import LoggingMixin
from geth.accounts import ensure_account_exists
from geth.chain import get_live_data_dir, get_chain_data_dir, initialize_chain, get_ropsten_data_dir
from geth.process import BaseGethProcess
from geth.wrapper import construct_test_chain_kwargs, get_max_socket_path_length, get_geth_binary_path
from web3 import Web3

from nucypher.config.constants import DEFAULT_CONFIG_ROOT


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


class NuCypherGethTestnetProcess(LoggingMixin, BaseGethProcess):  # FIXME

    ETH_ALLOCATION = str(Web3.fromWei(1000000000000000000000000000000, 'wei'))

    __CHAIN_NAME = 'testnet'
    __CHAIN_ID = 112358

    def __init__(self,
                 config_root: str = None,
                 overrides: dict = None):

        if overrides is None:
            overrides = dict()
        overrides.update({'network_id': str(self.__CHAIN_ID)})

        if 'data_dir' in overrides:
            raise ValueError(f"You cannot specify `data_dir` for a {self.__class__.__name__}")

        # Set the data dir
        if config_root is None:
            base_dir = os.path.join(DEFAULT_CONFIG_ROOT, '.ethereum')
        else:
            base_dir = os.path.join(config_root, '.ethereum')

        self.data_dir = get_chain_data_dir(base_dir=base_dir, name=self.__CHAIN_NAME)

        # Generate Geth CLI args
        geth_kwargs = construct_test_chain_kwargs(data_dir=self.data_dir, **overrides)

        # ensure that an account is present or crash
        coinbase = ensure_account_exists(**geth_kwargs)

        # Sanity Check
        assert get_live_data_dir() != self.data_dir   # not mainnet
        assert get_ropsten_data_dir != self.data_dir  # not ropsten

        #
        # Genesis
        #

        allocations = {"balance": str(self.ETH_ALLOCATION)}

        genesis_data = {
            "overwrite": True,

            "nonce": "0x0000000000000042",
            "timestamp": "0x0",
            "parentHash": "0x0000000000000000000000000000000000000000000000000000000000000000",
            "extraData": "0x",
            "gasLimit": "8000000",
            "difficulty": "2000",
            "mixhash": "0x0000000000000000000000000000000000000000000000000000000000000000",
            "coinbase": coinbase,
            "alloc": {
                coinbase: allocations,
            },
            "config": {
                "chainId": self.__CHAIN_ID,
                "homesteadBlock": 0,
                "eip155Block": 0,
                "eip158Block": 0,
                'daoForkBlock': 0,
                'daoForkSupport': True,
            }
        }

        initialize_chain(genesis_data, **geth_kwargs)
        super().__init__(geth_kwargs)
