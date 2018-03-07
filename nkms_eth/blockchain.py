from nkms_eth.config import PopulusConfig


class TheBlockchain:
    """
    http://populus.readthedocs.io/en/latest/config.html#chains

    mainnet: Connects to the public ethereum mainnet via geth.
    ropsten: Connects to the public ethereum ropsten testnet via geth.
    tester: Uses an ephemeral in-memory chain backed by pyethereum.
    testrpc: Uses an ephemeral in-memory chain backed by pyethereum.
    temp: Local private chain whos data directory is removed when the chain is shutdown. Runs via geth.
    """

    __network = ''
    __instance = None

    class AlreadyRunning(Exception):
        pass

    def __init__(self, populus_config: PopulusConfig=None, timeout=60):
        """
        Configures a populus project and connects to blockchain.network.
        Transaction timeouts specified measured in seconds.

        http://populus.readthedocs.io/en/latest/chain.wait.html

        """

        # Singleton
        if TheBlockchain.__instance is not None:
            message = 'Blockchain: is already running. Use .get() to retrieve'.format(self.__network)
            raise TheBlockchain.AlreadyRunning(message)
        TheBlockchain.__instance = self

        if populus_config is None:
            populus_config = PopulusConfig()

        self._populus_config = populus_config
        self._timeout = timeout
        self._project = populus_config.project

        # Opens and preserves connection to a running populus blockchain
        self._chain = self._project.get_chain(self.__network).__enter__()

    @classmethod
    def get(cls):
        if cls.__instance is None:
            class_name = cls.__name__
            raise Exception('{} has not been created.'.format(class_name))
        return cls.__instance

    def disconnect(self):
        self._chain.__exit__(None, None, None)

    def __del__(self):
        self.disconnect()

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(network={}, timeout={})"
        return r.format(class_name, self.__network, self._timeout)

    def get_contract(self, name):
        """
        Gets an existing contract from the network,
        or raises populus.contracts.exceptions.UnknownContract
        if there is no contract data available for the name/identifier.
        """
        return self._chain.provider.get_contract(name)

    def wait_time(self, wait_hours, step=50):
        """Wait the specified number of wait_hours by comparing block timestamps."""

        wait_seconds = wait_hours * 60 * 60
        current_block = self._chain.web3.eth.getBlock(self._chain.web3.eth.blockNumber)
        end_timestamp = current_block.timestamp + wait_seconds

        not_time_yet = True
        while not_time_yet:
            self._chain.wait.for_block(self._chain.web3.eth.blockNumber+step)
            current_block = self._chain.web3.eth.getBlock(self._chain.web3.eth.blockNumber)
            not_time_yet = current_block.timestamp < end_timestamp
