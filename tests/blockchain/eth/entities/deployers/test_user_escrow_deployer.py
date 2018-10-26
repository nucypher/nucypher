import os
import pytest
from nucypher.blockchain.eth.deployers import UserEscrowDeployer, UserEscrowProxyDeployer


@pytest.fixture(scope='function')
def user_escrow_proxy(three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    testerchain = policy_agent.blockchain
    deployer, alice, bob, *all_yall = testerchain.interface.w3.eth.accounts

    escrow_proxy_deployer = UserEscrowProxyDeployer(deployer_address=deployer,
                                                    secret_hash=os.urandom(32))

    _escrow_proxy_deployments_txhashes = escrow_proxy_deployer.deploy()
    testerchain.time_travel(seconds=120)
    yield escrow_proxy_deployer.contract_address
    testerchain.interface.registry.clear()
    testerchain.sever_connection()


@pytest.mark.usesfixtures('three_agents')
def test_user_escrow_deployer(three_agents, testerchain):
    deployer, alice, bob, *all_yall = testerchain.interface.w3.eth.accounts

    escrow_proxy_deployer = UserEscrowProxyDeployer(deployer_address=deployer,
                                                    secret_hash=os.urandom(32))

    _escrow_proxy_deployments_txhashes = escrow_proxy_deployer.deploy()

    deployer = UserEscrowDeployer(deployer_address=deployer)

    deployment_txhashes = deployer.deploy()

    for title, txhash in deployment_txhashes.items():
        receipt = testerchain.wait_for_receipt(txhash=txhash)
        assert receipt['status'] == 1, "Transaction Rejected {}:{}".format(title, txhash)


@pytest.mark.slow()
@pytest.mark.usesfixtures(['user_escrow_proxy', 'three_agents'])
def test_deploy_multiple(testerchain):
    deployer, alice, bob, *all_yall = testerchain.interface.w3.eth.accounts

    number_of_deployments = 100
    for index in range(number_of_deployments):
        deployer = UserEscrowDeployer(deployer_address=deployer)

        deployment_txhashes = deployer.deploy()

        for title, txhash in deployment_txhashes.items():
            receipt = testerchain.wait_for_receipt(txhash=txhash)
            assert receipt['status'] == 1, "Transaction Rejected {}:{}".format(title, txhash)

        # simulates passage of time / blocks
        if index % 15 == 0:
            testerchain.interface.w3.eth.web3.testing.mine(1)
            testerchain.time_travel(seconds=5)
