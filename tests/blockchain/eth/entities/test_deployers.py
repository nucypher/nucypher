import os

import pytest
from constant_sorrow import constants

from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent
from nucypher.blockchain.eth.constants import DISPATCHER_SECRET_LENGTH
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer, MinerEscrowDeployer, PolicyManagerDeployer, \
    ContractDeployer
from nucypher.blockchain.eth.interfaces import EthereumContractRegistry


def test_token_deployer_and_agent(testerchain):
    origin, *everybody_else = testerchain.interface.w3.eth.accounts

    # Trying to get token from blockchain before it's been published fails
    with pytest.raises(EthereumContractRegistry.UnknownContract):
        NucypherTokenAgent(blockchain=testerchain)

    # The big day...
    deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)

    # It's not armed
    with pytest.raises(NucypherTokenDeployer.ContractDeploymentError):
        deployer.deploy()

    # Token must be armed before deploying to the blockchain
    deployer.arm()
    deployer.deploy()

    # Create a token instance
    token_agent = deployer.make_agent()
    token_contract = testerchain.get_contract(token_agent.contract_name)

    expected_token_supply = token_contract.functions.totalSupply().call()
    assert expected_token_supply == token_agent.contract.functions.totalSupply().call()

    # Retrieve the token from the blockchain
    same_token_agent = NucypherTokenAgent(blockchain=testerchain)

    # Compare the contract address for equality
    assert token_agent.contract_address == same_token_agent.contract_address
    assert token_agent == same_token_agent  # __eq__

    testerchain.interface.registry.clear()


@pytest.mark.slow()
def test_deploy_ethereum_contracts(testerchain):

    origin, *everybody_else = testerchain.interface.w3.eth.accounts

    #
    # Nucypher Token
    #
    token_deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)
    assert token_deployer.deployer_address == origin

    with pytest.raises(ContractDeployer.ContractDeploymentError):
        assert token_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not token_deployer.is_armed
    assert not token_deployer.is_deployed

    token_deployer.arm()
    assert token_deployer.is_armed

    token_deployer.deploy()
    assert token_deployer.is_deployed
    assert len(token_deployer.contract_address) == 42

    token_agent = NucypherTokenAgent(blockchain=testerchain)
    assert len(token_agent.contract_address) == 42
    assert token_agent.contract_address == token_deployer.contract_address

    another_token_agent = token_deployer.make_agent()
    assert len(another_token_agent.contract_address) == 42
    assert another_token_agent.contract_address == token_deployer.contract_address == token_agent.contract_address

    #
    # Miner Escrow
    #
    miners_escrow_secret = os.urandom(DISPATCHER_SECRET_LENGTH)
    miner_escrow_deployer = MinerEscrowDeployer(
        token_agent=token_agent,
        deployer_address=origin,
        secret_hash=testerchain.interface.w3.sha3(miners_escrow_secret))
    assert miner_escrow_deployer.deployer_address == origin

    with pytest.raises(ContractDeployer.ContractDeploymentError):
        assert miner_escrow_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not miner_escrow_deployer.is_armed
    assert not miner_escrow_deployer.is_deployed

    miner_escrow_deployer.arm()
    assert miner_escrow_deployer.is_armed

    miner_escrow_deployer.deploy()
    assert miner_escrow_deployer.is_deployed
    assert len(miner_escrow_deployer.contract_address) == 42

    miner_agent = MinerAgent(token_agent=token_agent)
    assert len(miner_agent.contract_address) == 42
    assert miner_agent.contract_address == miner_escrow_deployer.contract_address

    another_miner_agent = miner_escrow_deployer.make_agent()
    assert len(another_miner_agent.contract_address) == 42
    assert another_miner_agent.contract_address == miner_escrow_deployer.contract_address == miner_agent.contract_address


    #
    # Policy Manager
    #
    policy_manager_secret = os.urandom(DISPATCHER_SECRET_LENGTH)
    policy_manager_deployer = PolicyManagerDeployer(
        miner_agent=miner_agent,
        deployer_address=origin,
        secret_hash=testerchain.interface.w3.sha3(policy_manager_secret))
    assert policy_manager_deployer.deployer_address == origin

    with pytest.raises(ContractDeployer.ContractDeploymentError):
        assert policy_manager_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not policy_manager_deployer.is_armed
    assert not policy_manager_deployer.is_deployed

    policy_manager_deployer.arm()
    assert policy_manager_deployer.is_armed

    policy_manager_deployer.deploy()
    assert policy_manager_deployer.is_deployed
    assert len(policy_manager_deployer.contract_address) == 42

    policy_agent = policy_manager_deployer.make_agent()
    assert len(policy_agent.contract_address) == 42
    assert policy_agent.contract_address == policy_manager_deployer.contract_address

    another_policy_agent = policy_manager_deployer.make_agent()
    assert len(another_policy_agent.contract_address) == 42
    assert another_policy_agent.contract_address == policy_manager_deployer.contract_address == policy_agent.contract_address
