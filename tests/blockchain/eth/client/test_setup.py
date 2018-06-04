from nucypher.blockchain.eth.deployers import NucypherTokenDeployer


def test_chain_creation(testerchain):
    # Ensure we are testing on the correct network...
    assert testerchain.interface.network == 'tester'

    # ... and that there are already some blocks mined
    assert testerchain.interface.w3.eth.blockNumber >= 0


def test_nucypher_contract_compiled(testerchain):
    # Ensure that solidity smart contacts are available, post-compile.
    token_contract_identifier = NucypherTokenDeployer(blockchain=testerchain)._contract_name
    assert token_contract_identifier in testerchain.interface._ControlCircumflex__raw_contract_cache
