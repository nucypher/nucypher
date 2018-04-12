import os

from os.path import join, dirname, abspath
from solc import compile_files
from solc import install_solc

from nkms.blockchain import eth


class SolidityConfig:
    version = 'v0.4.20'

    contract_names = ('Issuer',
                      'NuCypherKMSToken',
                      'MinersEscrow',
                      'PolicyManager',
                      'UserEscrow')

    __sol_binary_path = os.path.join(os.environ['VIRTUAL_ENV'], 'bin', 'solc')
    _source_dir = join(dirname(abspath(eth.__file__)), 'sol', 'source', 'contracts')

    def __init__(self):
        os.environ['SOLC_BINARY'] = self.__sol_binary_path

    def install_compiler(self):
        # https://github.com/ethereum/py-solc#installing-the-solc-binary
        return install_solc(self.version)


def compile_interfaces(config: SolidityConfig=SolidityConfig()) -> dict:

    contract_paths = [os.path.join(config._source_dir, contract+'.sol') for contract in config.contract_names]
    compiled_sol = compile_files(contract_paths)

    interfaces = dict()
    for contract_name, contract_path in zip(config.contract_names, contract_paths):
        contract_interface = compiled_sol['{}:{}'.format(contract_path, contract_name)]
        interfaces[contract_name] = contract_interface

    return interfaces
