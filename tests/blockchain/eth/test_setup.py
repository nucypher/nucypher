from nkms.blockchain.eth.deployers import NuCypherKMSTokenDeployer


def test_chain_creation(chain):
    # Ensure we are testing on the correct network...
    assert chain._network == 'tester'

    # ... and that there are already some blocks mined
    assert chain.provider.w3.eth.blockNumber >= 0


def test_nucypher_contract_compiled(chain):
    # Check that populus paths are set...

    # Ensure that solidity smart contacts are available, post-compile.
    token_contract_identifier = NuCypherKMSTokenDeployer(blockchain=chain)._contract_name
    assert token_contract_identifier in chain.provider._ContractProvider__raw_contract_cache
