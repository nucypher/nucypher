import glob
import itertools
import os
from pathlib import Path

from os.path import join, dirname, abspath
from solc import compile_files
from solc import install_solc

import nkms
from nkms.blockchain import eth

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
        join(Path.home(), 'Git', 'nucypher-kms', 'tests', 'blockchain', 'eth', 'contracts', 'contracts'),  # TODO: no
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

    compiled_sol = compile_files(sol_contract_paths)

    interfaces = dict()
    for contract_name, contract_path in zip(config.contract_names, sol_contract_paths):
        contract_interface = compiled_sol['{}:{}'.format(contract_path, contract_name)]
        interfaces[contract_name] = contract_interface

    return interfaces
