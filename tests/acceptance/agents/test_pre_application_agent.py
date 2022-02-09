import os
import pytest
from eth_utils import to_checksum_address, is_address

from nucypher.blockchain.eth.agents import PREApplicationAgent, ContractAgency
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower
from nucypher.types import StakingProviderInfo

MIN_AUTHORIZATION = 1
MIN_SECONDS = 1


def test_get_min_authorization(test_registry, application_economics):
    application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    result = application_agent.get_min_authorization()
    assert result == application_economics.min_authorization


def test_get_min_seconds(test_registry, application_economics):
    application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    result = application_agent.get_min_operator_seconds()
    assert result == application_economics.min_operator_seconds


def test_authorized_tokens(testerchain, application_economics, test_registry, staking_providers):
    application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    provider_account = staking_providers[0]
    authorized_amount = application_agent.get_authorized_stake(staking_provider=provider_account)
    assert authorized_amount >= application_economics.min_authorization


def test_staking_providers_and_operators_relationships(testerchain,
                                                       test_registry,
                                                       threshold_staking,
                                                       application_economics):
    application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)

    staking_provider_account, operator_account, *other = testerchain.unassigned_accounts
    tx = threshold_staking.functions.setRoles(staking_provider_account).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.authorizationIncreased(
        staking_provider_account, 0, application_economics.min_authorization).transact()
    testerchain.wait_for_receipt(tx)

    # The staking provider hasn't bond an operator yet
    assert NULL_ADDRESS == application_agent.get_operator_from_staking_provider(staking_provider=staking_provider_account)

    tpower = TransactingPower(account=staking_provider_account, signer=Web3Signer(testerchain.client))
    _txhash = application_agent.bond_operator(transacting_power=tpower,
                                              staking_provider=staking_provider_account,
                                              operator=operator_account)

    # We can check the staker-worker relation from both sides
    assert operator_account == application_agent.get_operator_from_staking_provider(staking_provider=staking_provider_account)
    assert staking_provider_account == application_agent.get_staking_provider_from_operator(operator_address=operator_account)

    # No staker-worker relationship
    random_address = to_checksum_address(os.urandom(20))
    assert NULL_ADDRESS == application_agent.get_operator_from_staking_provider(staking_provider=random_address)
    assert NULL_ADDRESS == application_agent.get_staking_provider_from_operator(operator_address=random_address)


def test_get_staker_population(staking_providers, test_registry):
    application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)

    # Apart from all the providers in the fixture, we also added a new provider above
    assert application_agent.get_staking_providers_population() == len(staking_providers) + 1


def test_get_swarm(staking_providers, test_registry):
    application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)

    swarm = application_agent.swarm()
    swarm_addresses = list(swarm)
    assert len(swarm_addresses) == len(staking_providers) + 1

    # Grab a staker address from the swarm
    provider_addr = swarm_addresses[0]
    assert isinstance(provider_addr, str)
    assert is_address(provider_addr)


@pytest.mark.usefixtures("staking_providers")
def test_sample_staking_providers(test_registry):
    application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)

    providers_population = application_agent.get_staking_providers_population()

    with pytest.raises(PREApplicationAgent.NotEnoughStakingProviders):
        application_agent.get_staking_provider_reservoir().draw(providers_population + 1)  # One more than we have deployed

    providers = application_agent.get_staking_provider_reservoir().draw(3)
    assert len(providers) == 3       # Three...
    assert len(set(providers)) == 3  # ...unique addresses

    # Same but with pagination
    providers = application_agent.get_staking_provider_reservoir(pagination_size=1).draw(3)
    assert len(providers) == 3
    assert len(set(providers)) == 3
    light = application_agent.blockchain.is_light
    application_agent.blockchain.is_light = not light
    providers = application_agent.get_staking_provider_reservoir().draw(3)
    assert len(providers) == 3
    assert len(set(providers)) == 3
    application_agent.blockchain.is_light = light


def test_get_staking_provider_info(testerchain, test_registry):
    application_agent = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    staking_provider_account, operator_account, *other = testerchain.unassigned_accounts
    info: StakingProviderInfo = application_agent.get_staking_provider_info(staking_provider=staking_provider_account)
    assert info.operator_start_timestamp > 0
    assert info.operator == operator_account
    assert not info.operator_confirmed
