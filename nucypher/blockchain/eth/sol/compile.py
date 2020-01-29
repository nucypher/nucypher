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
import collections
import os
import re
from typing import List, Set

import sys
from twisted.logger import Logger
from os.path import abspath, dirname

import itertools
import shutil

from nucypher.blockchain.eth.sol import SOLIDITY_COMPILER_VERSION

SourceDirs = collections.namedtuple('SourceDirs', ['root_source_dir',    # type: str
                                                   'other_source_dirs',  # type: Set[str]
                                                   ])
SourceDirs.__new__.__defaults__ = (None,)


class SolidityCompiler:

    __default_contract_version = 'v0.0.0'
    __default_contract_dir = os.path.join(dirname(abspath(__file__)), 'source')

    __compiled_contracts_dir = 'contracts'
    __zeppelin_library_dir = 'zeppelin'

    optimization_runs = 200

    class CompilerError(Exception):
        pass

    class VersionError(Exception):
        pass

    @classmethod
    def default_contract_dir(cls):
        return cls.__default_contract_dir

    def __init__(self,
                 solc_binary_path: str = None,
                 source_dirs: List[SourceDirs] = None,
                 ignore_solidity_check: bool = False
                 ) -> None:
        
        self.log = Logger('solidity-compiler')
        self._set_solc_binary_path(solc_binary_path)
        if not ignore_solidity_check:
            self._check_compiler_version()

        if source_dirs is None or len(source_dirs) == 0:
            self.source_dirs = [SourceDirs(root_source_dir=self.__default_contract_dir)]
        else:
            self.source_dirs = source_dirs

    def _set_solc_binary_path(self, solc_binary_path: str):
        # Compiler binary and root solidity source code directory
        self.__sol_binary_path = solc_binary_path
        if self.__sol_binary_path is None:
            self.__sol_binary_path = shutil.which('solc')
        if self.__sol_binary_path is None:
            bin_path = os.path.dirname(sys.executable)  # type: str
            self.__sol_binary_path = os.path.join(bin_path, 'solc')  # type: str

    def _check_compiler_version(self):
        from solc import get_solc_version_string
        raw_solc_version_string = get_solc_version_string(solc_binary=self.__sol_binary_path)
        solc_version_search = re.search(r"""
             Version:\s          # Beginning of the string
             (\d+\.\d+\.\d+)     # Capture digits of version
             \S+                 # Skip other info in version       
             """, raw_solc_version_string, re.VERBOSE
                                        )
        if not solc_version_search:
            raise SolidityCompiler.VersionError(f"Can't parse solidity version: {raw_solc_version_string}")
        solc_version = solc_version_search.group(1)
        if not solc_version == SOLIDITY_COMPILER_VERSION:
            raise SolidityCompiler.VersionError(f"Solidity version {solc_version} is unsupported. "
                                                f"Use {SOLIDITY_COMPILER_VERSION} or option to ignore this check")

    def compile(self) -> dict:
        interfaces = dict()
        for root_source_dir, other_source_dirs in self.source_dirs:
            if root_source_dir is None:
                self.log.warn("One of the root directories is None")
                continue

            raw_interfaces = self._compile(root_source_dir, other_source_dirs)
            for name, data in raw_interfaces.items():
                # Extract contract version from docs
                version_search = re.search(r"""
                
                \"details\":  # @dev tag in contract docs
                \".*?         # Skip any data in the beginning of details
                \|            # Beginning of version definition |
                (v            # Capture version starting from symbol v
                \d+           # At least one digit of major version
                \.            # Digits splitter
                \d+           # At least one digit of minor version
                \.            # Digits splitter
                \d+           # At least one digit of patch
                )             # End of capturing
                \|            # End of version definition |
                .*?\"         # Skip any data in the end of details
                
                """, data['devdoc'], re.VERBOSE)
                version = version_search.group(1) if version_search else self.__default_contract_version
                try:
                    existence_data = interfaces[name]
                except KeyError:
                    existence_data = dict()
                    interfaces.update({name: existence_data})
                if version not in existence_data:
                    existence_data.update({version: data})
        return interfaces

    def _compile(self, root_source_dir: str, other_source_dirs: [str]) -> dict:
        """Executes the compiler with parameters specified in the json config"""

        self.log.info("Using solidity compiler binary at {}".format(self.__sol_binary_path))
        contracts_dir = os.path.join(root_source_dir, self.__compiled_contracts_dir)
        self.log.info("Compiling solidity source files at {}".format(contracts_dir))

        source_paths = set()
        source_walker = os.walk(top=contracts_dir, topdown=True)
        if other_source_dirs is not None:
            for source_dir in other_source_dirs:
                other_source_walker = os.walk(top=source_dir, topdown=True)
                source_walker = itertools.chain(source_walker, other_source_walker)

        for root, dirs, files in source_walker:
            for filename in files:
                if filename.endswith('.sol'):
                    path = os.path.join(root, filename)
                    source_paths.add(path)
                    self.log.debug("Collecting solidity source {}".format(path))

        # Compile with remappings: https://github.com/ethereum/py-solc
        zeppelin_dir = os.path.join(root_source_dir, self.__zeppelin_library_dir)

        remappings = ("contracts={}".format(contracts_dir),
                      "zeppelin={}".format(zeppelin_dir),
                      )

        self.log.info("Compiling with import remappings {}".format(", ".join(remappings)))

        optimization_runs = self.optimization_runs
        from solc import compile_files
        from solc.exceptions import SolcError
        try:
            compiled_sol = compile_files(source_files=source_paths,
                                         solc_binary=self.__sol_binary_path,
                                         import_remappings=remappings,
                                         allow_paths=root_source_dir,
                                         optimize=True,
                                         optimize_runs=optimization_runs)

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
