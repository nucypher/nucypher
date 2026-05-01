import pytest

from nucypher.characters.lawful import Ursula
from nucypher.config.constants import TEMPORARY_DOMAIN_NAME
from tests.constants import MOCK_ETH_PROVIDER_URI, TESTERCHAIN_CHAIN_ID


def test_new_ursula_announces_herself(lonely_ursula_maker):
    ursula_in_a_house, ursula_with_a_mouse = lonely_ursula_maker(
        quantity=2, domain=TEMPORARY_DOMAIN_NAME
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


def test_no_corresponding_valid_condition_blockchain_provider(
    lonely_ursula_maker, mocker
):
    OTHER_CHAIN_ID = 66775827584859395569954838
    other_chain_uri = "this is an invalid provider URI, but doesn't matter because the health check will fail it"

    def mock_rpc_endpoint_health_check(endpoint: str, *args, **kwargs):
        if endpoint == other_chain_uri:
            return False

        return True

    mocker.patch(
        "nucypher.blockchain.eth.actors.rpc_endpoint_health_check",
        side_effect=mock_rpc_endpoint_health_check,
    )

    with pytest.raises(
        Ursula.ActorError,
        match=f"Operator-configured RPC condition endpoint.*{OTHER_CHAIN_ID}.* is unhealthy",
    ):
        _ursula_who_tries_to_connect_to_an_invalid_chain = lonely_ursula_maker(
            quantity=1,
            domain=TEMPORARY_DOMAIN_NAME,
            condition_blockchain_endpoints={
                TESTERCHAIN_CHAIN_ID: [MOCK_ETH_PROVIDER_URI],
                OTHER_CHAIN_ID: [other_chain_uri],
            },
        )
