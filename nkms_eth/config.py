from os.path import dirname, join, abspath

import appdirs
import populus

import nkms_eth


class PopulusConfig:

    def __init__(self):
        self._python_project_name = 'nucypher-kms'

        # This config is persistent and is created in user's .local directory
        self._registrar_path = join(appdirs.user_data_dir(self._python_project_name), 'registrar.json')

        # Populus project config
        self._project_dir = join(dirname(abspath(nkms_eth.__file__)), 'project')
        self._populus_project = populus.Project(self._project_dir)
        self.project.config['chains.mainnetrpc.contracts.backends.JSONFile.settings.file_path'] = self._registrar_path

    @property
    def project(self):
        return self._populus_project
