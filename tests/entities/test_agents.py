import pytest
from pytest import raises

from nkms_eth.deployers import NuCypherKMSTokenDeployer
from tests.utilities import spawn_miners, MockNuCypherMinerConfig

M = 10 ** 6


def test_deploy_miner_escrow(testerchain):

    token_deployer = NuCypherKMSTokenDeployer(blockchain=testerchain)

    with raises(NuCypherKMSTokenDeployer.ContractDeploymentError):
        token_deployer.deploy()

    token_deployer.arm()
    token_deployer.deploy()

    the_same_token_deployer = NuCypherKMSTokenDeployer.from_blockchain(blockchain=testerchain)

    with raises(NuCypherKMSTokenDeployer.ContractDeploymentError):
        the_same_token_deployer.arm()
        the_same_token_deployer.deploy()

    assert len(the_same_token_deployer.contract_address) == 42
    assert token_deployer.contract_address == the_same_token_deployer.contract_address


def test_get_swarm(testerchain, mock_token_deployer, miner_agent):

    mock_token_deployer._global_airdrop(amount=10000)

    creator, *addresses = testerchain._chain.web3.eth.accounts
    spawn_miners(addresses=addresses, miner_agent=miner_agent)

    default_period_duration = MockNuCypherMinerConfig._hours_per_period
    testerchain.wait_time(default_period_duration)

    swarm = miner_agent.swarm()
    swarm_addresses = list(swarm)
    assert len(swarm_addresses) == 9

    # Grab a miner address from the swarm
    miner_addr = swarm_addresses[0]
    assert isinstance(miner_addr, str)

    # Verify the address is hex
    try:
        int(miner_addr, 16)
    except ValueError:
        pytest.fail()


# ###### TODO
# def test_miner_agent(testerchain):
#     with raises(NoKnownAddress):
#         NuCypherKMSTokenAgent.get(blockchain=testerchain)
#
#     token = NuCypherKMSTokenAgent(blockchain=testerchain)
#     token.arm()
#     token.deploy()
#
#     same_token = NuCypherKMSTokenAgent.get(blockchain=testerchain)
#     with raises(NuCypherKMSTokenAgent.ContractDeploymentError):
#         same_token.arm()
#         same_token.deploy()
#
#     assert len(token.__contract.address) == 42
#     assert token.__contract.address == same_token._contract.address
#
#     with raises(NoKnownAddress):
#         MinerAgent.get(token=token)
#
#     escrow = MinerAgent(token=token)
#     escrow.arm()
#     escrow.deploy()
#
#     same_escrow = MinerAgent.get(token=token)
#     with raises(MinerAgent.ContractDeploymentError):
#         same_escrow.arm()
#         same_escrow.deploy()
#
#     assert len(escrow.__contract.address) == 42
#     assert escrow.__contract.address == same_escrow._contract.address

