from typing import List, Union

from constant_sorrow.constants import NO_BLOCKCHAIN_AVAILIBLE

from nucypher.blockchain.eth.constants import NucypherMinerConstants
from nucypher.blockchain.eth.interfaces import ContractInterface, DeployerInterface


class Blockchain:
    """A view of a blockchain through a provided interface"""

    _instance = NO_BLOCKCHAIN_AVAILIBLE
    __default_interface_class = ContractInterface

    test_chains = ('tester', )
    transient_chains = test_chains + ('testrpc', 'temp')
    public_chains = ('mainnet', 'ropsten')

    def __init__(self, interface: Union[ContractInterface, DeployerInterface]=None):

        if interface is NO_BLOCKCHAIN_AVAILIBLE:
            interface = self.__default_interface_class(blockchain_config=interface.config)

        self.__interface = interface
        self.config = interface.blockchain_config

        if self._instance is not None:
            raise RuntimeError("Local chain already running")
        else:
            Blockchain._instance = self

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(interface={})"
        return r.format(class_name, self.__interface)

    @classmethod
    def connect(cls):
        if cls._instance is None:
            raise RuntimeError('{} not running'.format(cls.__name__))
        return cls._instance

    @property
    def interface(self):
        return self.__interface

    @classmethod
    def sever(cls) -> None:
        cls._instance = None

    def get_contract(self, name):
        """
        Gets an existing contract from the registrar, or raises UnknownContract
        if there is no contract data available for the name/identifier.
        """
        return self.__interface.get_contract(name)

    def wait_for_receipt(self, txhash, timeout=None) -> dict:
        """Wait for a receipt and return it"""
        timeout = timeout if timeout is not None else self.config.timeout
        result = self.__interface.w3.eth.waitForTransactionReceipt(txhash, timeout=timeout)
        return result


class TesterBlockchain(Blockchain, NucypherMinerConstants):
    """
    Blockchain subclass with additional test utility methods
    and singleton-style instance caching to preserve the local blockchain state.
    """

    def wait_for_receipt(self, txhash, timeout=None) -> None:
        timeout = timeout if timeout is not None else self.config.timeout
        result = self.interface.w3.eth.waitForTransactionReceipt(txhash, timeout=timeout)
        return result

    def time_travel(self, hours: int=None, seconds: int=None, periods: int=None):
        """
        Wait the specified number of wait_hours by comparing
        block timestamps and mines a single block.
        """

        more_than_one_arg = sum(map(bool, (hours, seconds, periods))) > 1
        if more_than_one_arg:
            raise ValueError("Specify hours, seconds, or lock_periods, not a combination")

        if periods:
            duration = (self._hours_per_period * periods) * (60 * 60)
            base = self._hours_per_period * 60 * 60
        elif hours:
            duration = hours * (60 * 60)
            base = 60 * 60
        elif seconds:
            duration = seconds
            base = 1
        else:
            raise ValueError("Specify either hours, seconds, or lock_periods.")

        end_timestamp = ((self.interface.w3.eth.getBlock(block_identifier='latest').timestamp + duration) // base) * base
        self.interface.w3.eth.web3.testing.timeTravel(timestamp=end_timestamp)
        self.interface.w3.eth.web3.testing.mine(1)

    def ether_airdrop(self, amount: int) -> List[str]:
        """Airdrops tokens from creator address to all other addresses!"""

        coinbase, *addresses = self.__interface.w3.eth.accounts

        tx_hashes = list()
        for address in addresses:

            tx = {'to': address, 'from': coinbase, 'value': amount}
            txhash = self.interface.w3.eth.sendTransaction(tx)

            _receipt = self.wait_for_receipt(txhash)
            tx_hashes.append(txhash)

        return tx_hashes
