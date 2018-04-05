from os.path import join, dirname, abspath

import nkms_eth
from nkms_eth.deployers import NuCypherKMSTokenDeployer


def test_testerchain_creation(testerchain):
    # Ensure we are testing on the correct network...
    assert testerchain._network == 'tester'

    # ... and that there are already some blocks mined
    assert testerchain._chain.web3.eth.blockNumber >= 0


def test_nucypher_populus_project(testerchain):

    populus_project_dir = join(dirname(abspath(nkms_eth.__file__)), 'project')

    # Check that populus paths are set...

    # ...on the testerchain's config class
    assert testerchain._populus_config._project_dir == populus_project_dir

    # ...and on the testerchain/blockchain class itself
    assert testerchain._project.project_dir == populus_project_dir

    # Ensure that solidity smart contacts are available, post-compile.
    token_contract_identifier = NuCypherKMSTokenDeployer(blockchain=testerchain)._contract_name
    assert token_contract_identifier in testerchain._project.compiled_contract_data