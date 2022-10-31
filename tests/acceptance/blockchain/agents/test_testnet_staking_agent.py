import pytest
from web3 import Web3

from nucypher.blockchain.eth.agents import ContractAgency, TestnetThresholdStakingAgent, PREApplicationAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS


@pytest.fixture(scope='module')
def pre_application(agency, test_registry):
    pre_application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    return pre_application_agent


@pytest.fixture(scope='module')
def staking_provider(agency, test_registry, testerchain):
    return testerchain.unassigned_accounts[1]


def test_set_application(agency, test_registry, pre_application, deployer_transacting_power):
    testnet_staking_agent = ContractAgency.get_agent(TestnetThresholdStakingAgent, registry=test_registry)
    assert testnet_staking_agent.pre_application() == NULL_ADDRESS
    _receipt = testnet_staking_agent.set_application(contract_address=pre_application.contract.address,
                                                     transacting_power=deployer_transacting_power)
    assert testnet_staking_agent.pre_application() == pre_application.contract.address


def test_set_stakes(test_registry, staking_provider, deployer_transacting_power):
    testnet_staking_agent = ContractAgency.get_agent(TestnetThresholdStakingAgent, registry=test_registry)

    stakes = testnet_staking_agent.stakes(staking_provider=staking_provider)
    assert stakes.t_stake == 0
    assert stakes.keep_stake == 0
    assert stakes.nu_stake == 0

    t_stake = Web3.to_wei(40_000, 'ether')
    nu_stake = Web3.to_wei(15_000, 'ether')
    _receipt = testnet_staking_agent.set_stake(
        staking_provider=staking_provider,
        t_stake=t_stake,
        nu_stake=nu_stake,
        transacting_power=deployer_transacting_power
    )

    stakes = testnet_staking_agent.stakes(staking_provider=staking_provider)
    assert stakes.t_stake == t_stake
    assert stakes.keep_stake == 0
    assert stakes.nu_stake == nu_stake


def test_set_roles(test_registry, staking_provider, deployer_transacting_power):
    testnet_staking_agent = ContractAgency.get_agent(TestnetThresholdStakingAgent, registry=test_registry)

    roles = testnet_staking_agent.roles(staking_provider=staking_provider)
    assert roles.owner == NULL_ADDRESS
    assert roles.beneficiary == NULL_ADDRESS
    assert roles.authorizer == NULL_ADDRESS

    _receipt = testnet_staking_agent.set_roles(
        staking_provider=staking_provider,
        transacting_power=deployer_transacting_power
    )

    roles = testnet_staking_agent.roles(staking_provider=staking_provider)
    assert roles.owner == staking_provider
    assert roles.beneficiary == staking_provider
    assert roles.authorizer == staking_provider
