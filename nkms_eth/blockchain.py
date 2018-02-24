import populus
import threading
import nkms_eth
import appdirs
from os.path import dirname, join, abspath


class Blockchain:
    """
    http://populus.readthedocs.io/en/latest/config.html#chains

    mainnet: Connects to the public ethereum mainnet via geth.
    ropsten: Connects to the public ethereum ropsten testnet via geth.
    tester: Uses an ephemeral in-memory chain backed by pyethereum.
    testrpc: Uses an ephemeral in-memory chain backed by pyethereum.
    temp: Local private chain whos data directory is removed when the chain is shutdown. Runs via geth.

    """

    network = ''  # 'mainnetrpc'
    python_project_name = 'nucypher-kms'
    _project = threading.local()

    # This config is persistent and is created in user's .local directory
    registrar_path = join(appdirs.user_data_dir(python_project_name), 'registrar.json')

    def __init__(self, project_name='nucypher-kms', timeout=60):

        # Populus project config
        project_dir = join(dirname(abspath(nkms_eth.__file__)), 'project')
        project = populus.Project(project_dir)
        project.config['chains.mainnetrpc.contracts.backends.JSONFile.settings.file_path'] = self.registrar_path

        self.project_name = project_name
        self.timeout = timeout
        self.project_dir = project_dir
        self._project.project = project
        self._project.chain = self._project.project.get_chain(self.network).__enter__()

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(network={}, project_name={}, timeout={})"
        return r.format(class_name, self.network, self.project_name, self.timeout)

    def __str__(self):
        class_name = self.__class__.__name__
        return "{} {}:{}".format(class_name, self.network, self.project_name)

    def disconnect(self):
        self._project.chain.__exit__(None, None, None)

    @property
    def chain(self):
        return self._project.chain

    @property
    def web3(self):
        return self._project.chain.web3

    def get_contract(self, name):
        """ Gets an existing contract or returns an error """
        return self._project.chain.provider.get_contract(name)

    def wait_time(self, wait_hours, step=50):
        end_timestamp = self.web3.eth.getBlock(self.web3.eth.blockNumber).timestamp + wait_hours * 60 * 60
        not_time_yet = True
        while not_time_yet:
            self.chain.wait.for_block(self.web3.eth.blockNumber + step)
            not_time_yet = self.web3.eth.getBlock(self.web3.eth.blockNumber).timestamp < end_timestamp


class TesterBlockchain(Blockchain):
    network = 'tester'
