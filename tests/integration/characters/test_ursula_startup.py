import pytest


def test_new_ursula_announces_herself(lonely_ursula_maker):
    ursula_in_a_house, ursula_with_a_mouse = lonely_ursula_maker(
        quantity=2, domain="useless_domain"
    )

    # Neither Ursula knows about the other.
    assert ursula_with_a_mouse not in ursula_in_a_house.known_nodes
    assert ursula_in_a_house not in ursula_with_a_mouse.known_nodes

    ursula_in_a_house.remember_node(ursula_with_a_mouse)

    # OK, now, ursula_in_a_house knows about ursula_with_a_mouse, but not vice-versa.
    assert ursula_with_a_mouse in ursula_in_a_house.known_nodes
    assert ursula_in_a_house not in ursula_with_a_mouse.known_nodes

    # But as ursula_in_a_house learns, she'll announce herself to ursula_with_a_mouse.
    ursula_in_a_house.learn_from_teacher_node()

    assert ursula_with_a_mouse in ursula_in_a_house.known_nodes
    assert ursula_in_a_house in ursula_with_a_mouse.known_nodes


def test_node_deployer(ursulas):
    for ursula in ursulas:
        deployer = ursula.get_deployer()
        assert deployer.options['https_port'] == ursula.rest_information()[0].port
        assert deployer.application == ursula.rest_app


def test_goerli_and_mumbai_as_conditions_providers(lonely_ursula_maker):
    INVALID_CHAIN_ID = 66775827584859395569954838  # If we eventually support a chain with this ID, heaven help us.

    with pytest.raises(NotImplementedError):
        _ursula_who_tries_to_connect_to_an_invalid_chain = lonely_ursula_maker(
            quantity=1,
            domain="useless_domain",
            condition_blockchain_endpoints={
                INVALID_CHAIN_ID: "this is a provider URI, but it doesn't matter what we pass here because the chain_id is invalid."
            },
        )
