import glob
import itertools
import os
from pathlib import Path

from os.path import join, dirname, abspath
from solc import compile_files
from solc import install_solc

import nkms
from nkms.blockchain import eth
from tests.blockchain.eth import contracts


class SolidityConfig:
    version = 'v0.4.20'

    contract_names = ('Issuer',
                      'NuCypherKMSToken',
                      'MinersEscrow',
                      'PolicyManager',
                      'UserEscrow')

    __sol_binary_path = os.path.join(os.environ['VIRTUAL_ENV'], 'bin', 'solc')  # TODO: Does not work with pytest w/o intervention

    _contract_source_dirs = [
        join(dirname(abspath(eth.__file__)), 'sol', 'source', 'contracts'),
        join(os.path.dirname(os.path.abspath(contracts.__file__)), 'contracts')
    ]

    def __init__(self):
        os.environ['SOLC_BINARY'] = self.__sol_binary_path

    def install_compiler(self):
        # https://github.com/ethereum/py-solc#installing-the-solc-binary
        return install_solc(self.version)


def compile_interfaces(config: SolidityConfig=SolidityConfig()) -> dict:

    sol_contract_paths = list()
    for source_dir in config._contract_source_dirs:
        sol_contract_paths.extend(glob.iglob(source_dir+'/**/*.sol', recursive=True))

    compiled_sol = compile_files(sol_contract_paths, import_remappings=["contracts="+config._contract_source_dirs[0]]) # TODO

    interfaces = {name.split(':')[-1]: compiled_sol[name] for name in compiled_sol}

    return interfaces
