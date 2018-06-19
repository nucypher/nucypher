from nucypher.blockchain.eth.deployers import NucypherTokenDeployer


def test_chain_creation(chain):
    # Ensure we are testing on the correct network...
    assert chain.config.network == 'tester'

    # ... and that there are already some blocks mined
    assert chain.interface.w3.eth.blockNumber >= 0


def test_nucypher_contract_compiled(chain):
    # Ensure that solidity smart contacts are available, post-compile.
    token_contract_identifier = NucypherTokenDeployer(blockchain=chain)._contract_name
    assert token_contract_identifier in chain.interface._ContractInterface__raw_contract_cache
