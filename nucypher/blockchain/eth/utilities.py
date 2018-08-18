import os
import shutil
import tempfile
from typing import Dict

import pkg_resources
from constant_sorrow import constants
from eth.db import BaseDB
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
        self._swap_registry(filepath)                     # I'll allow it

        if os.path.exists(filepath):
            self.clear()                                  # clear prior sim runs

        _ = shutil.copy(self.temp_filepath, filepath)
        self.temp_filepath = constants.REGISTRY_COMMITED  # just in case
        return filepath


class OverridablePyEVMBackend(PyEVMBackend):
    """
    Work-around for eth-tester #88
    https://github.com/ethereum/eth-tester/issues/88

    Ad-hoc subclass eth-tester's PyEVMBackend to provide a
    facility for providing optional genesis state and params values at init-time.
    """

    def __init__(self,
                 genesis_params: dict = None,
                 genesis_state: dict = None) -> None:

        self.fork_config = {}

        if not is_pyevm_available():
            raise pkg_resources.DistributionNotFound(
                "The `py-evm` package is not available.  The "
                "`PyEVMBackend` requires py-evm to be installed and importable. "
                "Please install the `py-evm` library."
            )

        self.account_keys = constants.NO_BLOCKCHAIN
        self.chian = constants.NO_BLOCKCHAIN

        self.reset_to_genesis(param_overrides=genesis_params,  # type: Dict
                              state_overrides=genesis_state)   # type: Dict

    def reset_to_genesis(self,
                         param_overrides: dict = None,
                         state_overrides: dict = None) -> tuple:

        from eth.chains.base import MiningChain
        from eth.db import get_db_backend
        from eth.vm.forks.byzantium import ByzantiumVM

        class ByzantiumNoProofVM(ByzantiumVM):
            """Byzantium VM rules, without validating any miner proof of work"""

            @classmethod
            def validate_seal(self, header):
                pass

        class MainnetTesterNoProofChain(MiningChain):
            vm_configuration = ((0, ByzantiumNoProofVM),)

            @classmethod
            def validate_seal(cls, block):
                pass

        genesis_params = get_default_genesis_params()         # type: Dict
        account_keys = get_default_account_keys()             # type: Dict
        genesis_state = generate_genesis_state(account_keys)  # type: Dict

        if param_overrides is not None:
            genesis_params.update(param_overrides)

        if state_overrides is not None:
            genesis_state.update(state_overrides)

        base_db = get_db_backend()                            # type: BaseDB

        chain = MainnetTesterNoProofChain.from_genesis(base_db=base_db,
                                                       genesis_params=genesis_params,
                                                       genesis_state=genesis_state)

        self.account_keys, self.chain = account_keys, chain
        return self.account_keys, self.chain
