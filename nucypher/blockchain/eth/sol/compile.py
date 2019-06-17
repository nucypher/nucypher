"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import os

import sys
from twisted.logger import Logger
from os.path import abspath, dirname

import itertools
import shutil

try:
    from solc import install_solc, compile_files
    from solc.exceptions import SolcError
except ImportError:
    # TODO: Issue #461 and #758 - Include precompiled ABI; Do not use py-solc in standard installation
    pass


class SolidityCompiler:

    # TODO: Integrate with config classes

    __default_version = 'v0.5.3'
    __default_configuration_path = os.path.join(dirname(abspath(__file__)), './compiler.json')

    __default_sol_binary_path = shutil.which('solc')
    if __default_sol_binary_path is None:
        __bin_path = os.path.dirname(sys.executable)          # type: str
        __default_sol_binary_path = os.path.join(__bin_path, 'solc')  # type: str

    __default_contract_dir = os.path.join(dirname(abspath(__file__)), 'source', 'contracts')
    __default_chain_name = 'tester'

    def __init__(self,
                 solc_binary_path: str = None,
                 configuration_path: str = None,
                 chain_name: str = None,
                 source_dir: str = None,
                 test_contract_dir: str = None
                 ) -> None:

        self.log = Logger('solidity-compiler')
        # Compiler binary and root solidity source code directory
        self.__sol_binary_path = solc_binary_path if solc_binary_path is not None else self.__default_sol_binary_path
        self.source_dir = source_dir if source_dir is not None else self.__default_contract_dir
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

        self.log.info("Using solidity compiler binary at {}".format(self.__sol_binary_path))
        self.log.info("Compiling solidity source files at {}".format(self.source_dir))

        source_paths = set()
        source_walker = os.walk(top=self.source_dir, topdown=True)
        if self._test_solidity_source_dir:
            test_source_walker = os.walk(top=self._test_solidity_source_dir, topdown=True)
            source_walker = itertools.chain(source_walker, test_source_walker)

        for root, dirs, files in source_walker:
            for filename in files:
                if filename.endswith('.sol'):
                    path = os.path.join(root, filename)
                    source_paths.add(path)
                    self.log.debug("Collecting solidity source {}".format(path))

        # Compile with remappings: https://github.com/ethereum/py-solc
        project_root = dirname(self.source_dir)

        remappings = ("contracts={}".format(self.source_dir),
                      "zeppelin={}".format(os.path.join(project_root, 'zeppelin')),
                      )

        self.log.info("Compiling with import remappings {}".format(", ".join(remappings)))

        optimization_runs = 10  # TODO: Move..?
        try:
            compiled_sol = compile_files(source_files=source_paths,
                                         import_remappings=remappings,
                                         allow_paths=project_root,
                                         optimize=optimization_runs)

            self.log.info("Successfully compiled {} contracts with {} optimization runs".format(len(compiled_sol),
                                                                                                optimization_runs))

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
