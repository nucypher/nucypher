import populus
import threading
import nkms_eth
from os.path import dirname, join, abspath

DEFAULT_NETWORK = 'mainnetrpc'
_project = threading.local()


def project():
    # Hardcoded the config for the project
    # It will read user-specific configs also which may override it
    if not hasattr(_project, 'project'):
        project_dir = join(dirname(abspath(nkms_eth.__file__)), 'project')
        _project.project = populus.Project(project_dir, create_config_file=False)
    return _project.project


def chain(name=DEFAULT_NETWORK):
    if not hasattr(_project, 'chain'):
        _project.chain = project().get_chain(name).__enter__()
    return _project.chain


def disconnect():
    _project.chain.__exit__(None, None, None)
    delattr(_project, 'chain')


def web3():
    return chain().web3
