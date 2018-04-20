import distutils
import itertools
import os

from os.path import abspath, dirname
from solc import install_solc, compile_files


class SolidityCompiler:
    __default_version = 'v0.4.22'
    __default_configuration_path = os.path.join(dirname(abspath(__file__)), './compiler.json')

    __bin_path = os.path.dirname(distutils.spawn.find_executable('python'))
    __default_sol_binary_path = os.path.join(__bin_path, 'solc')

    __default_contract_dir = os.path.join(dirname(abspath(__file__)), 'source', 'contracts')
    __default_chain_name = 'tester'

    def __init__(self, solc_binary_path=None, configuration_path=None,
                 chain_name=None, contract_dir=None, test_contract_dir=None):

        # Compiler binary and root solidity source code directory
        self.__sol_binary_path = solc_binary_path if solc_binary_path is not None else self.__default_sol_binary_path
        self._solidity_source_dir = contract_dir if contract_dir is not None else self.__default_contract_dir
        self._test_solidity_source_dir = test_contract_dir

        # JSON config
        self.__configuration_path = configuration_path if configuration_path is not None else self.__default_configuration_path
        self._chain_name = chain_name if chain_name is not None else self.__default_chain_name

        # Set the local env's solidity compiler binary
        os.environ['SOLC_BINARY'] = self.__sol_binary_path

    def install_compiler(self, version=None):
        """
        Installs the specified solidity compiler version.
        https://github.com/ethereum/py-solc#installing-the-solc-binary
        """
        version = version if version is not None else self.__default_version
        return install_solc(version)  # TODO: fix path

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

        # Compile with remappings
        # https://github.com/ethereum/py-solc
        project_root = dirname(self._solidity_source_dir)

        remappings = ["contracts={}".format(self._solidity_source_dir),
                      "zeppelin={}".format(os.path.join(project_root, 'zeppelin')),
                      "proxy={}".format(os.path.join(project_root, 'proxy'))
                      ]

        compiled_sol = compile_files(source_files=source_paths,
                                     import_remappings=remappings,
                                     allow_paths=project_root,
                                     optimize=True)
                                     # libraries="AdditionalMath:0x00000000000000000000 Heap:0xABCDEF0123456"
                                     #           "LinkedList::0x00000000000000000000 Heap:0xABCDEF0123456")

        # Cleanup the compiled data keys
        interfaces = {name.split(':')[-1]: compiled_sol[name] for name in compiled_sol}
        return interfaces
