import populus
import threading
import nkms_eth
import appdirs
from os.path import dirname, join, abspath


class Blockchain:
    network = 'mainnetrpc'
    project_name = 'nucypher-kms'
    _project = threading.local()
    registrar_path = join(appdirs.user_data_dir(project_name), 'registrar.json')    # Persistent; In user's .local dir

    class NotEnoughUrsulas(Exception):
        pass

    def __init__(self, project_name='nucypher-kms', timeout=60):
        self.project_name = project_name
        self.timeout = timeout

        project_dir = join(dirname(abspath(nkms_eth.__file__)), 'project')
        project = populus.Project(project_dir)
        project.config['chains.mainnetrpc']['contracts']['backends']['JSONFile']['settings']['file_path'] = self.registrar_path

        self.project_dir = project_dir
        self._project.project = project
        self._project.chain = project.get_chain(self.network)

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(network={}, project_name={}, timeout={})"
        return r.format(class_name, self.network, self.project_name, self.timeout)

    def __str__(self):
        return f"{self.__class__.__name__} {self.network}:{self.project_name}"

    def __enter__(self):
        return self._project.chain.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._project.chain.__exit__(None, None, None)

    def __del__(self):
        for attr in ('project', 'chain', 'w3'):
            if hasattr(self._project, attr):
                delattr(self._project, attr)

    def get_contract(self, name):
        """ Gets an existing contract or returns an error """
        with self as chain:
            return chain.provider.get_contract(name)


class TesterBlockchain(Blockchain):
    network = 'tester'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
