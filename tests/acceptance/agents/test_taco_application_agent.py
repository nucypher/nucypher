import os

import pytest
from eth_utils import is_address, to_checksum_address

from nucypher.blockchain.eth.agents import TACoApplicationAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower


def test_get_min_authorization(taco_application_agent, taco_application):
    result = taco_application_agent.get_min_authorization()
    assert result == taco_application.minimumAuthorization()


def test_get_min_seconds(taco_application_agent, taco_application):
    result = taco_application_agent.get_min_operator_seconds()
    assert result == taco_application.minOperatorSeconds()


def test_authorized_tokens(
    testerchain, taco_application, taco_application_agent, staking_providers
):
    provider_account = staking_providers[0]
    authorized_amount = taco_application_agent.get_authorized_stake(
        staking_provider=provider_account
    )
    assert authorized_amount >= taco_application.minimumAuthorization()


def test_staking_providers_and_operators_relationships(
    testerchain,
    taco_application_agent,
    threshold_staking,
    taco_application,
    deployer_account,
):
    staking_provider_account, operator_account, *other = testerchain.unassigned_accounts
    threshold_staking.setRoles(staking_provider_account, sender=deployer_account)
    threshold_staking.authorizationIncreased(
        staking_provider_account,
        0,
        taco_application.minimumAuthorization(),
        sender=deployer_account,
    )

    # The staking provider hasn't bond an operator yet
    assert NULL_ADDRESS == taco_application_agent.get_operator_from_staking_provider(
        staking_provider=staking_provider_account
    )

    tpower = TransactingPower(
        account=staking_provider_account, signer=Web3Signer(testerchain.client)
    )
    _txhash = taco_application_agent.bond_operator(
        transacting_power=tpower,
        staking_provider=staking_provider_account,
        operator=operator_account,
    )

    # We can check the staker-worker relation from both sides
    assert (
        operator_account
        == taco_application_agent.get_operator_from_staking_provider(
            staking_provider=staking_provider_account
        )
    )
    assert (
        staking_provider_account
        == taco_application_agent.get_staking_provider_from_operator(
            operator_address=operator_account
        )
    )

    # No staker-worker relationship
    random_address = to_checksum_address(os.urandom(20))
    assert NULL_ADDRESS == taco_application_agent.get_operator_from_staking_provider(
        staking_provider=random_address
    )


def test_get_staker_population(taco_application_agent, staking_providers):
    # Apart from all the providers in the fixture, we also added a new provider above
    assert (
        taco_application_agent.get_staking_providers_population()
        == len(staking_providers) + 1
    )


def test_get_swarm(taco_application_agent, staking_providers):
    swarm = taco_application_agent.swarm()
    swarm_addresses = list(swarm)
    assert len(swarm_addresses) == len(staking_providers) + 1

    # Grab a staker address from the swarm
    provider_addr = swarm_addresses[0]
    assert isinstance(provider_addr, str)
    assert is_address(provider_addr)


@pytest.mark.usefixtures("staking_providers", "ursulas")
def test_sample_staking_providers(taco_application_agent):
    providers_population = taco_application_agent.get_staking_providers_population()

    with pytest.raises(TACoApplicationAgent.NotEnoughStakingProviders):
        taco_application_agent.get_staking_provider_reservoir().draw(
            providers_population + 1
        )  # One more than we have deployed

    providers = taco_application_agent.get_staking_provider_reservoir().draw(3)
    assert len(providers) == 3  # Three...
    assert len(set(providers)) == 3  # ...unique addresses

    # Same but with pagination
    providers = taco_application_agent.get_staking_provider_reservoir(
        pagination_size=1
    ).draw(3)
    assert len(providers) == 3
    assert len(set(providers)) == 3
    light = taco_application_agent.blockchain.is_light
    taco_application_agent.blockchain.is_light = not light
    providers = taco_application_agent.get_staking_provider_reservoir().draw(3)
    assert len(providers) == 3
    assert len(set(providers)) == 3
    taco_application_agent.blockchain.is_light = light


def test_get_staking_provider_info(testerchain, taco_application_agent):
    staking_provider_account, operator_account, *other = testerchain.unassigned_accounts
    info: TACoApplicationAgent.StakingProviderInfo = (
        taco_application_agent.get_staking_provider_info(
            staking_provider=staking_provider_account
        )
    )
    assert info.operator_start_timestamp > 0
    assert info.operator == operator_account
    assert not info.operator_confirmed
