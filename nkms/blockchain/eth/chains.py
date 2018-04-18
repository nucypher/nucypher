import random
from abc import ABC

from nkms.blockchain.eth.interfaces import ContractProvider


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
        return self.config.provider.get_contract(name)

    def wait_for_receipt(self, txhash, timeout=None) -> None:
        if timeout is None:
            timeout = self._default_timeout

        result = self.provider.w3.eth.waitForTransactionReceipt(txhash)

        return result


class TesterBlockchain(TheBlockchain):
    """Transient, in-memory, local, private chain"""

    _network = 'tester'
    __default_nodes = 9
    __insecure_passphrase = 'this-is-not-a-secure-password'

    def __init__(self, nodes: int=__default_nodes, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__node_addresses = list()
        for _ in range(nodes):
            address = self.provider.w3.personal.newAccount(self.__insecure_passphrase)
            self.provider.w3.personal.unlockAccount(address, self.__insecure_passphrase)
            self.__node_addresses.append(address)
        self.__global_airdrop(amount=1000000)

    def wait_time(self, hours=None, seconds=None):
        """Wait the specified number of wait_hours by comparing block timestamps."""
        if hours:
            duration = hours * 60 * 60
        elif seconds:
            duration = seconds
        else:
            raise Exception("Invalid time")

        end_timestamp = self.provider.w3.eth.getBlock('latest').timestamp + duration
        self.provider.w3.eth.web3.testing.timeTravel(end_timestamp)
        self.provider.w3.eth.web3.testing.mine(1)

    def spawn_miners(self, miner_agent, addresses: list, locktime: int, random_amount=False) -> list:

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
                min_stake = miner_agent._min_allowed_locked    #TODO
                max_stake = miner_agent._max_allowed_locked
                amount = random.randint(min_stake, max_stake)
            else:
                amount = miner.token_balance() // 2    # stake half
            miner.stake(amount=amount, locktime=locktime, auto_switch_lock=True)

        return miners

    def __global_airdrop(self, amount: int) -> None:
        """Airdrops from creator address to all other addresses!"""
        coinbase, *addresses = self.provider.w3.eth.accounts

        for address in addresses:
            tx = {'to': address,
                  'from': coinbase,
                  'value': amount}
            _txhash = self.provider.w3.eth.sendTransaction(tx)



#
# class TestRPCBlockchain:
#
#     _network = 'testrpc'
#     _default_timeout = 60
#
