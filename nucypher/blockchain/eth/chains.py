from typing import List, Union

from constant_sorrow import constants
from web3.middleware import geth_poa_middleware

from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainDeployerInterface
from nucypher.config.blockchain import BlockchainConfiguration
from nucypher.config.parsers import parse_blockchain_config


class Blockchain:
    """A view of a blockchain through a provided interface"""

    _instance = None
    _default_network = NotImplemented
    __default_interface_class = BlockchainInterface

    test_chains = ('tester', 'temp')
    public_chains = ('mainnet', 'ropsten')

    class ConnectionNotEstablished(RuntimeError):
        pass

    def __init__(self, interface: Union[BlockchainInterface, BlockchainDeployerInterface]=None) -> None:

        if interface is None:
            interface = self.__default_interface_class()
        self.__interface = interface

        # Singelton
        if self._instance is None:
            Blockchain._instance = self
        else:
            raise RuntimeError("Local chain already running")

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(interface={})"
        return r.format(class_name, self.__interface)

    @classmethod
    def from_config(cls, config: BlockchainConfiguration) -> 'Blockchain':
        pass

    @classmethod
    def from_config_file(cls, filepath: str):
        config = BlockchainConfiguration.from_config_file(filepath=filepath)
        interface = BlockchainInterface.from_config(config=config)

        if cls._instance is not None:
            return cls.connect()

        if config.tester is True:
            from nucypher.utilities.sandbox.blockchain import TesterBlockchain
            blockchain = TesterBlockchain(interface=interface,
                                          poa=config.poa,
                                          test_accounts=config.test_accounts,
                                          airdrop=config.airdrop)
        else:
            blockchain = Blockchain(interface=interface)

        return blockchain

    @classmethod
    def connect(cls, from_config=True, config_filepath: str=None):
        if cls._instance is None:
            if from_config:
                return cls.from_config_file(filepath=config_filepath)
            else:
                raise cls.ConnectionNotEstablished('A connection has not yet been established. init the blockchain.')
        return cls._instance

    @property
    def interface(self):
        return self.__interface

    def attach_interface(self, interface: Union[BlockchainInterface, BlockchainDeployerInterface]):
        if self.__interface is not None:
            raise RuntimeError('There is already an attached blockchain interface')
        self.__interface = interface

    def get_contract(self, name):
        """
        Gets an existing contract from the registrar, or raises UnknownContract
        if there is no contract data available for the name/identifier.
        """
        return self.__interface.get_contract_by_name(name)

    def wait_for_receipt(self, txhash, timeout=None) -> dict:
        """Wait for a receipt and return it"""
        timeout = timeout if timeout is not None else self.interface.timeout
        result = self.__interface.w3.eth.waitForTransactionReceipt(txhash, timeout=timeout)
        return result

    def unlock_account(self, address, password, duration):
        return self.interface.w3.personal.unlockAccount(address, password, duration)
