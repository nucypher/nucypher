import os
import shutil
from os.path import abspath, dirname

import itertools
from solc import install_solc, compile_files
from solc.exceptions import SolcError


class SolidityCompiler:

    # TODO: Integrate with config classes

    __default_version = 'v0.4.24'
    __default_configuration_path = os.path.join(dirname(abspath(__file__)), './compiler.json')

    __default_sol_binary_path = shutil.which('solc')
    if __default_sol_binary_path is None:
        __bin_path = os.path.dirname(shutil.which('python'))          # type: str
        __default_sol_binary_path = os.path.join(__bin_path, 'solc')  # type: str

    __default_contract_dir = os.path.join(dirname(abspath(__file__)), 'source', 'contracts')
    __default_chain_name = 'tester'

    def __init__(self,
                 solc_binary_path: str = None,
                 configuration_path: str = None,
                 chain_name: str = None,
                 contract_dir: str = None,
                 test_contract_dir: str= None
                 ) -> None:

        # Compiler binary and root solidity source code directory
        self.__sol_binary_path = solc_binary_path if solc_binary_path is not None else self.__default_sol_binary_path
        self._solidity_source_dir = contract_dir if contract_dir is not None else self.__default_contract_dir
        self._test_solidity_source_dir = test_contract_dir

        # JSON config
        self.__configuration_path = configuration_path if configuration_path is not None else self.__default_configuration_path
        self._chain_name = chain_name if chain_name is not None else self.__default_chain_name

        # Set the local env's solidity compiler binary
        os.environ['SOLC_BINARY'] = self.__sol_binary_path

    def install_compiler(self, version: str=None):
        """
        Installs the specified solidity compiler version.
        https://github.com/ethereum/py-solc#installing-the-solc-binary
        """
        version = version if version is not None else self.__default_version
        return install_solc(version, platform=None)  # TODO: fix path

    def compile(self) -> dict:
        """Executes the compiler with parameters specified in the json config"""

        source_paths = set()
        source_walker = os.walk(top=self._solidity_source_dir, topdown=True)
        if self._test_solidity_source_dir:
            test_source_walker = os.walk(top=self._test_solidity_source_dir, topdown=True)
            source_walker = itertools.chain(source_walker, test_source_walker)

        for root, dirs, files in source_walker:
            for filename in files:
                if filename.endswith('.sol'):
                    source_paths.add(os.path.join(root, filename))

        # Compile with remappings: https://github.com/ethereum/py-solc
        project_root = dirname(self._solidity_source_dir)

        remappings = ("contracts={}".format(self._solidity_source_dir),
                      "zeppelin={}".format(os.path.join(project_root, 'zeppelin')),
                      )
        try:
            compiled_sol = compile_files(source_files=source_paths,
                                         import_remappings=remappings,
                                         allow_paths=project_root,
                                         optimize=10)
        except FileNotFoundError:
            raise RuntimeError("The solidity compiler is not at the specified path. "
                               "Check that the file exists and is executable.")
        except PermissionError:
            raise RuntimeError("The solidity compiler binary at {} is not executable. "
                               "Check the file's permissions.".format(self.__sol_binary_path))

        except SolcError:
            raise

        # Cleanup the compiled data keys
        interfaces = {name.split(':')[-1]: compiled_sol[name] for name in compiled_sol}
        return interfaces
