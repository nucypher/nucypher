import glob
import os

from os.path import join, dirname, abspath
from solc import compile_files
from solc import install_solc

from nkms.blockchain import eth
from nkms.config.configs import _DEFAULT_CONFIGURATION_DIR
from tests.blockchain.eth import contracts


class SolidityCompiler:
    __default_version = 'v0.4.21'
    __default_configuration_path = os.path.join(_DEFAULT_CONFIGURATION_DIR, 'compiler.json')
    __default_sol_binary_path = os.path.join(os.environ['VIRTUAL_ENV'], 'bin', 'solc')   # TODO: Does not work with pytest w/o intervention

    def __init__(self, solc_binary_path=None, configuration_path=None):
        solc_binary_path = solc_binary_path if solc_binary_path is not None else self.__default_sol_binary_path
        configuration_path = configuration_path if configuration_path is not None else self.__default_configuration_path

        self.__sol_binary_path = solc_binary_path
        os.environ['SOLC_BINARY'] = self.__sol_binary_path

        self.__configuration_path = configuration_path

        self._contract_source_dirs = [  # TODO: Deprecate for standard compile
            join(dirname(abspath(eth.__file__)), 'sol', 'source', 'contracts'),
            join(os.path.dirname(os.path.abspath(contracts.__file__)), 'contracts')
        ]

    def install_compiler(self, version=None):
        """
        Installs the specified solidity compiler version.
        https://github.com/ethereum/py-solc#installing-the-solc-binary
        """
        version = version if version is not None else self.__default_version
        return install_solc(version)  # TODO: fix path

    @classmethod
    def from_json_config(self):
        pass

    def compile(self) -> dict:
        """Executes the compiler"""
        sol_contract_paths = list()
        for source_dir in self._contract_source_dirs:
            sol_contract_paths.extend(glob.iglob(source_dir + '/**/*.sol', recursive=True))

        remapping_dirs = ["contracts={}".format(self._contract_source_dirs[0])]
        compiled_sol = compile_files(sol_contract_paths, import_remappings=remapping_dirs)

        interfaces = {name.split(':')[-1]: compiled_sol[name] for name in compiled_sol}

        return interfaces
