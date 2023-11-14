import random

import pytest

from nucypher.blockchain.eth.constants import NULL_ADDRESS


def test_get_min_authorization(
    taco_child_application_agent, taco_child_application, taco_application
):
    result = taco_child_application_agent.get_min_authorization()
    assert result == taco_child_application.minimumAuthorization()
    assert result == taco_application.minimumAuthorization()


def test_authorized_tokens(
    testerchain, taco_application, taco_child_application_agent, staking_providers
):
    provider_account = staking_providers[0]
    authorized_amount = taco_child_application_agent.get_authorized_stake(
        staking_provider=provider_account
    )
    assert authorized_amount >= taco_application.minimumAuthorization()


def test_staking_provider_from_operator(
    taco_child_application_agent, ursulas, get_random_checksum_address
):
    for ursula in ursulas:
        assert (
            ursula.checksum_address
            == taco_child_application_agent.staking_provider_from_operator(
                ursula.operator_address
            )
        )

    assert NULL_ADDRESS == taco_child_application_agent.staking_provider_from_operator(
        operator_address=get_random_checksum_address()
    )


def test_staking_provider_info(
    taco_child_application_agent,
    ursulas,
    get_random_checksum_address,
):
    staking_providers = taco_child_application_agent.get_staking_providers()

    for ursula in ursulas:
        provider_info = taco_child_application_agent.staking_provider_info(
            ursula.checksum_address
        )
        assert provider_info.operator_confirmed is True
        assert provider_info.operator == ursula.operator_address
        assert (
            provider_info.authorized
            >= taco_child_application_agent.get_min_authorization()
        )
        assert (
            provider_info.index == staking_providers.index(ursula.checksum_address) + 1
        )

    provider_info = taco_child_application_agent.staking_provider_info(
        get_random_checksum_address()
    )
    assert provider_info.operator_confirmed is False
    assert provider_info.operator == NULL_ADDRESS
    assert provider_info.authorized == 0


def test_is_operator_confirmed(
    taco_child_application_agent, ursulas, get_random_checksum_address
):
    # ursulas are indeed confirmed
    for ursula in ursulas:
        assert (
            taco_child_application_agent.is_operator_confirmed(ursula.operator_address)
            is True
        )

    # random addresses are not
    assert (
        taco_child_application_agent.is_operator_confirmed(
            operator_address=NULL_ADDRESS
        )
        is False
    )
    assert (
        taco_child_application_agent.is_operator_confirmed(
            operator_address=get_random_checksum_address()
        )
        is False
    )


def test_get_staker_population(taco_child_application_agent, staking_providers):
    # Apart from all the providers in the fixture, we also added a new provider above
    assert taco_child_application_agent.get_staking_providers_population() == len(
        staking_providers
    )


@pytest.mark.usefixtures("staking_providers", "ursulas")
def test_sample_staking_providers(taco_child_application_agent):
    all_staking_providers = taco_child_application_agent.get_staking_providers()
    providers_population = (
        taco_child_application_agent.get_staking_providers_population()
    )

    with pytest.raises(taco_child_application_agent.NotEnoughStakingProviders):
        taco_child_application_agent.get_staking_provider_reservoir().draw(
            providers_population + 1
        )  # One more than we have deployed

    providers = taco_child_application_agent.get_staking_provider_reservoir().draw(3)
    assert len(providers) == 3  # Three...
    assert len(set(providers)) == 3  # ...unique addresses
    assert len(set(providers).intersection(all_staking_providers)) == 3

    # Same but with pagination
    providers = taco_child_application_agent.get_staking_provider_reservoir(
        pagination_size=1
    ).draw(3)
    assert len(providers) == 3
    assert len(set(providers)) == 3
    assert len(set(providers).intersection(all_staking_providers)) == 3

    # repeat for opposite blockchain light setting
    light = taco_child_application_agent.blockchain.is_light
    taco_child_application_agent.blockchain.is_light = not light
    providers = taco_child_application_agent.get_staking_provider_reservoir().draw(3)
    assert len(providers) == 3
    assert len(set(providers)) == 3
    assert len(set(providers).intersection(all_staking_providers)) == 3
    taco_child_application_agent.blockchain.is_light = light

    # Use exclusion list
    exclude_providers = random.choices(all_staking_providers, k=2)  # exclude 2 ursulas
    providers = taco_child_application_agent.get_staking_provider_reservoir(
        without=exclude_providers, pagination_size=1
    ).draw(3)
    assert len(providers) == 3
    assert len(set(providers)) == 3
    assert len(set(providers).intersection(all_staking_providers)) == 3
    assert len(set(providers).intersection(exclude_providers)) == 0
