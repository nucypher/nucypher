import pytest

from nucypher.characters.lawful import Ursula
from nucypher.config.constants import TEMPORARY_DOMAIN_NAME
from tests.constants import TESTERCHAIN_CHAIN_ID


def test_new_ursula_announces_herself(lonely_ursula_maker, accounts):
    ursula_in_a_house, ursula_with_a_mouse = lonely_ursula_maker(
        domain=TEMPORARY_DOMAIN_NAME,
        accounts=accounts,
        quantity=2,
    )

    # Neither Ursula knows about the other.
    assert ursula_with_a_mouse not in ursula_in_a_house.peers
    assert ursula_in_a_house not in ursula_with_a_mouse.peers

    ursula_in_a_house.remember_peer(ursula_with_a_mouse)

    # OK, now, ursula_in_a_house knows about ursula_with_a_mouse, but not vice-versa.
    assert ursula_with_a_mouse in ursula_in_a_house.peers
    assert ursula_in_a_house not in ursula_with_a_mouse.peers

    # But as ursula_in_a_house learns, she'll announce herself to ursula_with_a_mouse.
    ursula_in_a_house.learn_from_peer()

    assert ursula_with_a_mouse in ursula_in_a_house.peers
    assert ursula_in_a_house in ursula_with_a_mouse.peers


def test_node_deployer(ursulas):
    for ursula in ursulas:
        deployer = ursula.get_deployer()
        assert deployer.options['https_port'] == ursula.rest_information()[0].port
        assert deployer.application == ursula.rest_app


def test_no_corresponding_condition_blockchain_provider(lonely_ursula_maker, accounts):
    INVALID_CHAIN_ID = 66775827584859395569954838  # If we eventually support a chain with this ID, heaven help us.

    with pytest.raises(Ursula.ActorError):
        _ursula_who_tries_to_connect_to_an_invalid_chain = lonely_ursula_maker(
            accounts=accounts,
            quantity=1,
            domain=TEMPORARY_DOMAIN_NAME,
            condition_blockchain_endpoints={
                TESTERCHAIN_CHAIN_ID: "this is a provider URI.",
                INVALID_CHAIN_ID: "this is a provider URI, but it doesn't matter what we pass here because the chain_id is invalid."
            },
        )
