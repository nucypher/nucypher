from nucypher.blockchain.eth.constants import NULL_ADDRESS


def test_staking_provider_from_operator(taco_child_application_agent, ursulas):
    for ursula in ursulas:
        assert (
            ursula.checksum_address
            == taco_child_application_agent.staking_provider_from_operator(
                ursula.operator_address
            )
        )


def test_staking_provider_info(
    taco_child_application_agent,
    ursulas,
    taco_application_proxy,
    get_random_checksum_address,
):
    for ursula in ursulas:
        provider_info = taco_child_application_agent.staking_provider_info(
            ursula.checksum_address
        )
        assert provider_info.operator_confirmed is True
        assert provider_info.operator == ursula.operator_address
        assert provider_info.authorized >= taco_application_proxy.minimumAuthorization()

    # non-existing staking provider
    # TODO is this right? Technically this is what the contract returns
    #  Should returned info be "None"; although we don't really expect this situation
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
