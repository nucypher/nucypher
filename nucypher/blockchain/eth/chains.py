from typing import List, Union

from constant_sorrow import constants
from web3.middleware import geth_poa_middleware

from nucypher.blockchain.eth.interfaces import ControlCircumflex, DeployerCircumflex


class Blockchain:
    """A view of a blockchain through a provided interface"""

    _instance = None
    _default_network = NotImplemented
    __default_interface_class = ControlCircumflex

    test_chains = ('tester', )
    transient_chains = test_chains + ('testrpc', 'temp')
    public_chains = ('mainnet', 'ropsten')

    class ConnectionNotEstablished(RuntimeError):
        pass

    def __init__(self, interface: Union[ControlCircumflex, DeployerCircumflex]=None):

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
    def connect(cls):
        if cls._instance is None:
            raise cls.ConnectionNotEstablished('A connection has not yet been established. init the blockchain.')
        return cls._instance

    @classmethod
    def sever_connection(cls) -> None:
        cls._instance = None

    @property
    def interface(self):
        return self.__interface

    def attach_interface(self, interface: Union[ControlCircumflex, DeployerCircumflex]):
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
        return self.interface.w3.personal.unlockAccount(
            address, password, duration)


class TesterBlockchain(Blockchain):
    """
    Blockchain subclass with additional test utility methods and options.
    """
    __default_num_test_accounts = 10
    _default_network = 'tester'

    def __init__(self, test_accounts=None, poa=False, airdrop=False, *args, **kwargs):

        # Depends on circumflex
        super().__init__(*args, **kwargs)

        # For use with Proof Of Authority test-blockchains
        if poa is True:
            w3 = self.interface.w3
            w3.middleware_stack.inject(geth_poa_middleware, layer=0)

        # Generate additional ethereum accounts for testing
        if len(self.interface.w3.eth.accounts) == 1:
            from tests.blockchain.eth import utilities

            test_accounts = test_accounts if test_accounts is not None else self.__default_num_test_accounts
            utilities.generate_accounts(w3=self.interface.w3, quantity=test_accounts-1)

        assert test_accounts == len(self.interface.w3.eth.accounts)

        if airdrop is True:  # ETH for everyone!
            one_million_ether = 10 ** 6 * 10 ** 18  # wei -> ether
            self.ether_airdrop(amount=one_million_ether)

    def ether_airdrop(self, amount: int) -> List[str]:
        """Airdrops ether from creator address to all other addresses!"""

        coinbase, *addresses = self.interface.w3.eth.accounts

        tx_hashes = list()
        for address in addresses:

            tx = {'to': address, 'from': coinbase, 'value': amount}
            txhash = self.interface.w3.eth.sendTransaction(tx)

            _receipt = self.wait_for_receipt(txhash)
            tx_hashes.append(txhash)

        return tx_hashes

    def time_travel(self, hours: int=None, seconds: int=None, periods: int=None):
        """
        Wait the specified number of wait_hours by comparing
        block timestamps and mines a single block.
        """

        more_than_one_arg = sum(map(bool, (hours, seconds, periods))) > 1
        if more_than_one_arg:
            raise ValueError("Specify hours, seconds, or lock_periods, not a combination")

        if periods:
            duration = (constants.HOURS_PER_PERIOD * periods) * (60*60)
            base = constants.HOURS_PER_PERIOD * 60 * 60
        elif hours:
            duration = hours * (60*60)
            base = 60 * 60
        elif seconds:
            duration = seconds
            base = 1
        else:
            raise ValueError("Specify either hours, seconds, or lock_periods.")

        now = self.interface.w3.eth.getBlock(block_identifier='latest').timestamp
        end_timestamp = ((now+duration)//base) * base

        self.interface.w3.eth.web3.testing.timeTravel(timestamp=end_timestamp)
        self.interface.w3.eth.web3.testing.mine(1)

    def unlock_account(self, address, password, duration):
        # Test accounts are unlocked anyway.
        return True
