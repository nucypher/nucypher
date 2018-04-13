from os.path import join, dirname, abspath
from nkms.blockchain.eth.deployers import NuCypherKMSTokenDeployer


def test_testerchain_creation(testerchain):
    # Ensure we are testing on the correct network...
    assert testerchain._network == 'tester'

    # ... and that there are already some blocks mined
    assert testerchain.provider.web3.eth.blockNumber >= 0


def test_nucypher_contract_compiled(testerchain):
    # Check that populus paths are set...

    # Ensure that solidity smart contacts are available, post-compile.
    token_contract_identifier = NuCypherKMSTokenDeployer(blockchain=testerchain)._contract_name
    assert token_contract_identifier in testerchain.provider._Provider__contract_cache