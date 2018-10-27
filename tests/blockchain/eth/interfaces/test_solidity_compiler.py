from nucypher.blockchain.eth.deployers import NucypherTokenDeployer


def test_nucypher_contract_compiled(testerchain):
    # Ensure that solidity smart contacts are available, post-compile.
    origin, *everybody_else = testerchain.interface.w3.eth.accounts

    token_contract_identifier = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)._contract_name
    assert token_contract_identifier in testerchain.interface._BlockchainInterface__raw_contract_cache
