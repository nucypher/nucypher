import pytest
import os
import nkms_eth
from populus import Project


@pytest.fixture()
def project():
    project_dir = os.path.dirname(os.path.abspath(nkms_eth.__file__))
    project_dir = os.path.join(project_dir, 'project')
    return Project(project_dir, create_config_file=True)
