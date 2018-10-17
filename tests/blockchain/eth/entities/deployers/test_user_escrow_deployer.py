import os
import random

import pytest

from nucypher.blockchain.eth.constants import MIN_ALLOWED_LOCKED, MAX_MINTING_PERIODS, MIN_LOCKED_PERIODS
from nucypher.blockchain.eth.deployers import UserEscrowDeployer, UserEscrowProxyDeployer


@pytest.fixture(scope='function')
def user_escrow_proxy(three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    testerchain = policy_agent.blockchain
    deployer, alice, bob, *all_yall = testerchain.interface.w3.eth.accounts

    escrow_proxy_deployer = UserEscrowProxyDeployer(deployer_address=deployer,
                                                    policy_agent=policy_agent,
                                                    secret_hash=os.urandom(32))
    assert escrow_proxy_deployer.arm()
    _escrow_proxy_deployments_txhashes = escrow_proxy_deployer.deploy()
    testerchain.time_travel(seconds=120)
    yield escrow_proxy_deployer.contract_address
    testerchain.interface.registry.clear()
    testerchain.sever_connection()


def test_user_escrow_proxy_deployer():
    pass


def test_user_escrow_deployer(three_agents, testerchain):
    token_agent, miner_agent, policy_agent = three_agents
    deployer, alice, bob, *all_yall = testerchain.interface.w3.eth.accounts

    # Depends on UserEscrowProxy Deployment (and thus Linker, too)
    # with pytest.raises(testerchain.interface.registry.UnknownContract):
    # deployer = UserEscrowDeployer(policy_agent=policy_agent,
    #                               deployer_address=deployer)

    escrow_proxy_deployer = UserEscrowProxyDeployer(deployer_address=deployer,
                                                    policy_agent=policy_agent,
                                                    secret_hash=os.urandom(32))
    assert escrow_proxy_deployer.arm()
    _escrow_proxy_deployments_txhashes = escrow_proxy_deployer.deploy()

    deployer = UserEscrowDeployer(policy_agent=policy_agent,
                                  deployer_address=deployer)
    assert deployer.arm()
    deployment_txhashes = deployer.deploy()

    for title, txhash in deployment_txhashes.items():
        receipt = testerchain.wait_for_receipt(txhash=txhash)
        assert receipt['status'] == 1, "Transaction Rejected {}:{}".format(title, txhash)


@pytest.mark.slow()
@pytest.mark.usesfixtures('user_escrow_proxy')
def test_deploy_multiple(three_agents, testerchain):
    token_agent, miner_agent, policy_agent = three_agents
    deployer, alice, bob, *all_yall = testerchain.interface.w3.eth.accounts

    number_of_deployments = 100
    for index in range(number_of_deployments):
        deployer = UserEscrowDeployer(policy_agent=policy_agent,
                                      deployer_address=deployer)
        assert deployer.arm()
        deployment_txhashes = deployer.deploy()

        for title, txhash in deployment_txhashes.items():
            receipt = testerchain.wait_for_receipt(txhash=txhash)
            assert receipt['status'] == 1, "Transaction Rejected {}:{}".format(title, txhash)

        # simulates passage of time / blocks
        if index % 15 == 0:
            testerchain.interface.w3.eth.web3.testing.mine(1)
            testerchain.time_travel(seconds=5)


@pytest.mark.slow()
# @pytest.mark.usesfixtures('user_escrow_proxy')
def test_deploy_and_allocate(three_agents, user_escrow_proxy):
    token_agent, miner_agent, policy_agent = three_agents
    testerchain = policy_agent.blockchain
    origin, alice, bob, *all_yall = testerchain.interface.w3.eth.accounts

    deployments = dict()
    allocation = MIN_ALLOWED_LOCKED * 1
    number_of_deployments = 1

    _last_deployment_address = None
    for index in range(number_of_deployments):
        escrow_deployer = UserEscrowDeployer(policy_agent=policy_agent,
                                             deployer_address=origin)
        escrow_deployer.arm()
        _deployment_txhashes = escrow_deployer.deploy()

        # Ensure we have the correct assembly of address and abi
        assert escrow_deployer.principal_contract.address != escrow_deployer.contract.address
        # assert escrow_deployer.contract_address == user_escrow_proxy  # (address)

        # Ensure each deployment is unique
        if _last_deployment_address:
            assert escrow_deployer.principal_contract.address != _last_deployment_address
        _last_deployment_address = escrow_deployer.principal_contract.address

        deployments[escrow_deployer.principal_contract.address] = escrow_deployer
    assert len(deployments) == number_of_deployments

    # Let some time pass
    testerchain.time_travel(hours=3)
    assert token_agent.get_balance(address=origin) > 1

    # Start allocating tokens
    deposit_txhashes, approve_hashes = dict(), dict()
    for address, deployer in deployments.items():
        assert deployer.deployer_address == origin

        deposit_txhash = deployer.initial_deposit(value=allocation, duration=MAX_MINTING_PERIODS)
        receipt = testerchain.wait_for_receipt(txhash=deposit_txhash)
        assert receipt['status'] == 1, "Transaction Rejected {}".format(deposit_txhash)
        deposit_txhashes[address] = deposit_txhash

        beneficiary = random.choice(all_yall)
        assignment_txhash = deployer.assign_beneficiary(beneficiary)
        receipt = testerchain.wait_for_receipt(txhash=assignment_txhash)
        assert receipt['status'] == 1, "Transaction Rejected {}".format(assignment_txhash)

    assert len(deposit_txhashes) == number_of_deployments == len(deployments)
