import random
from abc import ABC
from typing import List

from nucypher.blockchain.eth.constants import NucypherMinerConfig
from nucypher.blockchain.eth.interfaces import ContractProvider


class TheBlockchain(ABC):
    """
    http://populus.readthedocs.io/en/latest/config.html#chains

    mainnet: Connects to the public ethereum mainnet via geth.
    ropsten: Connects to the public ethereum ropsten testnet via geth.
    tester: Uses an ephemeral in-memory chain backed by pyethereum.
    testrpc: Uses an ephemeral in-memory chain backed by pyethereum.
    temp: Local private chain whos data directory is removed when the chain is shutdown. Runs via geth.
    """

    _network = NotImplemented
    _default_timeout = 120
    __instance = None

    test_chains = ('tester', )
    transient_chains = test_chains + ('testrpc', 'temp')
    public_chains = ('mainnet', 'ropsten')

    class IsAlreadyRunning(RuntimeError):
        pass

    def __init__(self, contract_provider: ContractProvider):

        """
        Configures a populus project and connects to blockchain.network.
        Transaction timeouts specified measured in seconds.

        http://populus.readthedocs.io/en/latest/chain.wait.html
        """

        # Singleton #
        if TheBlockchain.__instance is not None:
            message = '{} is already running on {}. Use .get() to retrieve'.format(self.__class__.__name__,
                                                                                   self._network)
            raise TheBlockchain.IsAlreadyRunning(message)
        TheBlockchain.__instance = self

        self.provider = contract_provider

    @classmethod
    def get(cls):
        if cls.__instance is None:
            class_name = cls.__name__
            raise Exception('{} has not been created.'.format(class_name))
        return cls.__instance

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(network={})"
        return r.format(class_name, self._network)

    def get_contract(self, name):
        """
        Gets an existing contract from the registrar,
        or raises populus.contracts.exceptions.UnknownContract
        if there is no contract data available for the name/identifier.
        """
        return self.provider.get_contract(name)

    def wait_for_receipt(self, txhash, timeout=None) -> None:
        timeout = timeout if timeout is not None else self._default_timeout
        result = self.provider.w3.eth.waitForTransactionReceipt(txhash, timeout=timeout)
        return result


class TesterBlockchain(TheBlockchain, NucypherMinerConfig):
    """Transient, in-memory, local, private chain"""

    _network = 'tester'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def wait_for_receipt(self, txhash, timeout=None) -> None:
        timeout = timeout if timeout is not None else self._default_timeout
        result = self.provider.w3.eth.waitForTransactionReceipt(txhash, timeout=timeout)
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
        elif hours:
            duration = hours * (60 * 60)
        elif seconds:
            duration = seconds
        else:
            raise ValueError("Specify either hours, seconds, or lock_periods.")

        end_timestamp = self.provider.w3.eth.getBlock(block_identifier='latest').timestamp + duration
        self.provider.w3.eth.web3.testing.timeTravel(timestamp=end_timestamp)
        self.provider.w3.eth.web3.testing.mine(1)

    def _global_airdrop(self, amount: int) -> List[str]:
        """Airdrops from creator address to all other addresses!"""
        coinbase, *addresses = self.provider.w3.eth.accounts

        tx_hashes = list()
        for address in addresses:
            tx = {'to': address, 'from': coinbase, 'value': amount}
            txhash = self.provider.w3.eth.sendTransaction(tx)
            _receipt = self.provider.w3.eth.waitForTransactionReceipt(txhash)
            tx_hashes.append(txhash)
        for txhash in tx_hashes:
            self.wait_for_receipt(txhash)
        return tx_hashes

#
# class TestRPCBlockchain:
#
#     _network = 'testrpc'
#     _default_timeout = 60
#
