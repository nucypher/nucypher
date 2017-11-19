import populus
import threading
import nkms_eth
from os.path import dirname, join, abspath

DEFAULT_NETWORK = 'mainnetrpc'
TIMEOUT = 60
_project = threading.local()


# TODO XXX registrar.json is created in a current directory!
# we should instead create all new configs in ~/.local


def project():
    # Hardcoded the config for the project
    # It will read user-specific configs also which may override it
    if not hasattr(_project, 'project'):
        project_dir = join(dirname(abspath(nkms_eth.__file__)), 'project')
        _project.project = populus.Project(project_dir, create_config_file=False)
    return _project.project


def get_chain(name=None):
    return project().get_chain(name or DEFAULT_NETWORK)


def chain(name=None):
    if not hasattr(_project, 'chain'):
        _project.chain = get_chain(name).__enter__()
    return _project.chain


def disconnect():
    _project.chain.__exit__(None, None, None)
    if hasattr(_project, 'project'):
        delattr(_project, 'project')
    if hasattr(_project, 'chain'):
        delattr(_project, 'chain')
    if hasattr(_project, 'web3'):
        delattr(_project, 'web3')


def web3():
    return chain().web3
