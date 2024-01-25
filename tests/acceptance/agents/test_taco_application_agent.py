import random

import pytest

from nucypher.blockchain.eth.agents import TACoApplicationAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS


def test_get_min_authorization(taco_application_agent, taco_application):
    result = taco_application_agent.get_min_authorization()
    assert result == taco_application.minimumAuthorization()


def test_get_min_seconds(taco_application_agent, taco_application):
    result = taco_application_agent.get_min_operator_seconds()
    assert result == taco_application.minOperatorSeconds()


def test_staking_providers_and_operators_relationships(
    testerchain,
    taco_application_agent,
    threshold_staking,
    taco_application,
    deployer_account,
    get_random_checksum_address,
):
    staking_provider_wallet = testerchain.accounts.unassigned_wallets[0]
    operator_wallet = testerchain.accounts.unassigned_wallets[1]

    threshold_staking.setRoles(staking_provider_wallet.address, sender=deployer_account)
    threshold_staking.authorizationIncreased(
        staking_provider_wallet.address,
        0,
        taco_application.minimumAuthorization(),
        sender=deployer_account,
    )

    # The staking provider hasn't bonded an operator yet
    assert NULL_ADDRESS == taco_application_agent.get_operator_from_staking_provider(
        staking_provider=staking_provider_wallet.address
    )

    _txhash = taco_application_agent.bond_operator(
        wallet=staking_provider_wallet,
        staking_provider=staking_provider_wallet.address,
        operator=operator_wallet.address,
    )

    # We can check the staker-worker relation from both sides
    assert (
        operator_wallet.address
        == taco_application_agent.get_operator_from_staking_provider(
            staking_provider=staking_provider_wallet.address
        )
    )
    assert (
        staking_provider_wallet.address
        == taco_application_agent.get_staking_provider_from_operator(
            operator_address=operator_wallet.address
        )
    )

    # No staker-worker relationship
    assert NULL_ADDRESS == taco_application_agent.get_operator_from_staking_provider(
        staking_provider=get_random_checksum_address()
    )


def test_authorized_tokens(
    testerchain, taco_application, taco_application_agent, accounts
):
    provider_wallet = accounts.unassigned_wallets[0]
    authorized_amount = taco_application_agent.get_authorized_stake(
        staking_provider=provider_wallet.address
    )
    assert authorized_amount >= taco_application.minimumAuthorization()


@pytest.mark.usefixtures("bond_operators", "ursulas")
def test_get_staker_population(taco_application_agent, accounts):
    # Apart from all the providers in the fixture, we also added a new provider above
    assert (
            taco_application_agent.get_staking_providers_population()
            == len(accounts.stake_provider_wallets) + 1
    )


@pytest.mark.usefixtures("bond_operators", "ursulas")
def test_sample_staking_providers(taco_application_agent):
    all_staking_providers = list(taco_application_agent.get_staking_providers())
    providers_population = taco_application_agent.get_staking_providers_population()

    assert len(all_staking_providers) == providers_population

    with pytest.raises(taco_application_agent.NotEnoughStakingProviders):
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
    assert len(set(providers).intersection(all_staking_providers)) == 3

    # Use exclusion list
    exclude_providers = random.choices(all_staking_providers, k=3)  # exclude 3 ursulas
    providers = taco_application_agent.get_staking_provider_reservoir(
        without=exclude_providers, pagination_size=1
    ).draw(3)
    assert len(providers) == 3
    assert len(set(providers)) == 3
    assert len(set(providers).intersection(all_staking_providers)) == 3
    assert len(set(providers).intersection(exclude_providers)) == 0


def test_get_staking_provider_info(
    testerchain, taco_application_agent, get_random_checksum_address
):
    staking_provider_wallet = testerchain.accounts.stake_provider_wallets[0]
    operator_wallet = testerchain.accounts.ursula_wallets[0]

    info: TACoApplicationAgent.StakingProviderInfo = (
        taco_application_agent.get_staking_provider_info(
            staking_provider=staking_provider_wallet.address
        )
    )
    assert info.operator_start_timestamp > 0
    assert info.operator == operator_wallet.address
    assert info.operator_confirmed is True

    # non-existent staker
    info = taco_application_agent.get_staking_provider_info(
        get_random_checksum_address()
    )
    assert info.operator_start_timestamp == 0
    assert info.operator == NULL_ADDRESS
    assert info.operator_confirmed is False
