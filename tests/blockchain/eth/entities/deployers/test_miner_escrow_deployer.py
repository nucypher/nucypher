import os

import pytest

from nucypher.blockchain.eth.agents import MinerAgent
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer, MinerEscrowDeployer


def test_token_deployer_and_agent(testerchain):
    origin, *everybody_else = testerchain.interface.w3.eth.accounts

    # The big day...
    token_deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)

    token_deployer.deploy()

    secret_hash = os.urandom(32)
    deployer = MinerEscrowDeployer(blockchain=testerchain,
                                   deployer_address=origin,
                                   secret_hash=secret_hash)

    deployment_txhashes = deployer.deploy()

    for title, txhash in deployment_txhashes.items():
        receipt = testerchain.wait_for_receipt(txhash=txhash)
        assert receipt['status'] == 1, "Transaction Rejected {}:{}".format(title, txhash)

    # Create a token instance
    miner_agent = deployer.make_agent()
    miner_escrow_contract = miner_agent.contract

    expected_token_supply = miner_escrow_contract.functions.totalSupply().call()
    assert expected_token_supply == miner_agent.contract.functions.totalSupply().call()

    # Retrieve the token from the blockchain
    same_miner_agent = MinerAgent()

    # Compare the contract address for equality
    assert miner_agent.contract_address == same_miner_agent.contract_address
    assert miner_agent == same_miner_agent  # __eq__

    testerchain.interface.registry.clear()
