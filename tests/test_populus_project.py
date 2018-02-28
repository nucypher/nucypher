from os.path import join, dirname, abspath

import nkms_eth


def test_testerchain_create(testerchain):
    assert testerchain._network == 'tester'
    assert testerchain._chain.web3.eth.blockNumber >= 0


def test_nucypher_populus_project(testerchain):
    project_dir = join(dirname(abspath(nkms_eth.__file__)), 'project')

    assert testerchain._populus_config._project_dir == project_dir           # blockchain instance
    assert testerchain._project.project_dir == project_dir                   # populus project

    # raw compiled contract access
    assert 'NuCypherKMSToken' in testerchain._project.compiled_contract_data