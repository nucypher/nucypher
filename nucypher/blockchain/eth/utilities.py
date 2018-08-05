import os
import shutil
import tempfile

import pkg_resources
from eth_tester import PyEVMBackend
from eth_tester.backends import is_pyevm_available
from eth_tester.backends.pyevm.main import get_default_genesis_params, get_default_account_keys, generate_genesis_state

from nucypher.blockchain.eth.interfaces import EthereumContractRegistry


class TemporaryEthereumContractRegistry(EthereumContractRegistry):

    def __init__(self):
        _, self.temp_filepath = tempfile.mkstemp()
        super().__init__(registry_filepath=self.temp_filepath)

    def clear(self):
        with open(self.registry_filepath, 'w') as registry_file:
            registry_file.write('')

    def reset(self):
        os.remove(self.temp_filepath)  # remove registrar tempfile

    def commit(self, filepath) -> str:
        """writes the current state of the registry to a file"""
        return shutil.copy(self.temp_filepath, filepath)


class OverridablePyEVMBackend(PyEVMBackend):

    def __init__(self, genesis_overrides=None):
        """
        Example overrides
        ---------------------------------
        coinbase: address_bytes
        difficulty: int(default: 131072)
        extra_data: bytes
        gas_limit: int(default: 3141592)
        gas_used: int(default: 0)
        nonce: bytes
        block_number: int
        timestamp: int(epoch)
        """

        self.fork_config = dict()

        if not is_pyevm_available():
            raise pkg_resources.DistributionNotFound(
                "The `py-evm` package is not available.  The "
                "`PyEVMBackend` requires py-evm to be installed and importable. "
                "Please install the `py-evm` library."
            )

        self.reset_to_genesis(overrides=genesis_overrides)

    def reset_to_genesis(self, overrides=None):
        from evm.chains.tester import MainnetTesterChain
        from evm.db import get_db_backend

        base_db = get_db_backend()
        genesis_params = get_default_genesis_params()

        # Genesis params overrides
        if overrides is not None:
            genesis_params.update(overrides)

        account_keys = get_default_account_keys()
        genesis_state = generate_genesis_state(account_keys)
        chain = MainnetTesterChain.from_genesis(base_db, genesis_params, genesis_state)

        self.account_keys, self.chain = account_keys, chain