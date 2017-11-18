import pytest
from nkms_eth import blockchain


@pytest.fixture()
def project():
    blockchain.DEFAULT_NETWORK = 'tester'
    return blockchain.project()
