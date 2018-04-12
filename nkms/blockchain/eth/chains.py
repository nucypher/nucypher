import random
from abc import ABC

from nkms.config.configs import EthereumConfig


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
    _default_timeout = NotImplemented
    __instance = None

    test_chains = ('tester', )
    transient_chains = test_chains + ('testrpc', 'temp')
    public_chains = ('mainnet', 'ropsten')

    class IsAlreadyRunning(RuntimeError):
        pass

    def __init__(self, config: EthereumConfig):
        """
        Configures a populus project and connects to blockchain.network.
        Transaction timeouts specified measured in seconds.

        http://populus.readthedocs.io/en/latest/chain.wait.html

        """

        # Singleton
        if TheBlockchain.__instance is not None:
            message = '{} is already running on {}. Use .get() to retrieve'.format(self.__class__.__name__, self._network)
            raise TheBlockchain.IsAlreadyRunning(message)
        TheBlockchain.__instance = self

        self.config = config

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
        return self.config.provider.get_contract(name)

    def wait_for_receipt(self, txhash, timeout=None) -> None:
        if timeout is None:
            timeout = self._default_timeout

        result = self.config.wait.for_receipt(txhash, timeout=timeout)
        return result


class TesterBlockchain(TheBlockchain):
    """Transient, in-memory, local, private chain"""

    _network = 'tester'

    def wait_time(self, wait_hours, step=50):
        """Wait the specified number of wait_hours by comparing block timestamps."""

        end_timestamp = self.config.web3.eth.getBlock(
            self._chain.web3.eth.blockNumber).timestamp + wait_hours * 60 * 60
        while self._chain.web3.eth.getBlock(self._chain.web3.eth.blockNumber).timestamp < end_timestamp:
            self._chain.wait.for_block(self._chain.web3.eth.blockNumber + step)

    def spawn_miners(self, miner_agent, addresses: list, locktime: int, random_amount=False) -> list():
        """
        Deposit and lock a random amount of tokens in the miner escrow
        from each address, "spawning" new Miners.
        """
        from nkms.blockchain.eth.actors import Miner

        miners = list()
        for address in addresses:
            miner = Miner(miner_agent=miner_agent, address=address)
            miners.append(miner)

            if random_amount is True:
                amount = (10 + random.randrange(9000)) * miner_agent._deployer._M
            else:
                amount = miner.token_balance() // 2    # stake half
            miner.stake(amount=amount, locktime=locktime, auto_switch_lock=True)

        return miners

    def _global_airdrop(self, token_agent, amount: int):
        """Airdrops from creator address to all other addresses!"""

        _creator, *addresses = self._chain.web3.eth.accounts

        def txs():
            for address in addresses:
                txhash = token_agent.transact({'from': token_agent.origin}).transfer(address, amount)
                yield txhash

        receipts = list()
        for tx in txs():    # One at a time
            receipt = self.wait_for_receipt(tx)
            receipts.append(receipt)
        return receipts



#
# class TestRPCBlockchain:
#
#     _network = 'testrpc'
#     _default_timeout = 60
#
