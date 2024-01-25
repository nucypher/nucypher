import pytest
from eth_utils import to_checksum_address
from twisted.logger import LogLevel, globalLogPublisher

from nucypher.acumen.nicknames import Nickname
from nucypher.acumen.perception import FleetSensor
from nucypher.characters.unlawful import Vladimir
from nucypher.config.constants import TEMPORARY_DOMAIN_NAME
from nucypher.network.middleware import RestMiddleware
from tests.constants import MOCK_ETH_PROVIDER_URI
from tests.utils.middleware import EvilMiddleWare, MockRestMiddleware


def test_all_ursulas_know_about_all_other_ursulas(ursulas, test_registry):
    """
    Once launched, all Ursulas know about - and can help locate - all other Ursulas in the network.
    """
    onchain_records = [
        (u.staking_provider_address, )
        for u in ursulas
    ]

    for record in onchain_records:
        address = to_checksum_address(record[0])   #TODO: something better
        for propagating_ursula in ursulas[:1]:  # Last Ursula is not staking
            if address == propagating_ursula.checksum_address:
                continue
            else:
                assert address in propagating_ursula.peers.addresses(), "{} did not know about {}". \
                    format(propagating_ursula, Nickname.from_seed(address))


def test_alice_finds_ursula_via_rest(alice, ursulas):
    # Imagine alice knows of nobody.
    alice._Learner__peers = FleetSensor(domain=TEMPORARY_DOMAIN_NAME)

    alice.remember_peer(ursulas[0])
    alice.learn_from_peer()
    assert len(alice.peers) == len(ursulas)

    for ursula in ursulas:
        assert ursula in alice.peers


@pytest.mark.usefixtures("monkeypatch_get_staking_provider_from_operator")
def test_vladimir_illegal_interface_key_does_not_propagate(ursulas):
    """
    Although Ursulas propagate each other's interface information, as demonstrated above,
    they do not propagate interface information for Vladimir.

    Specifically, if Vladimir tries to perform the most obvious imitation attack -
    propagating his own wallet address along with Ursula's information - the validity
    check will catch it and Ursula will refuse to propagate it and also record Vladimir's
    details.
    """

    warnings = []

    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    ursulas = list(ursulas)
    ursula_whom_vladimir_will_imitate, other_ursula = ursulas[0], ursulas[1]

    # Vladimir sees Ursula on the network and tries to use her public information.
    vladimir = Vladimir.from_target_ursula(ursula_whom_vladimir_will_imitate)

    # This Ursula is totally legit...
    ursula_whom_vladimir_will_imitate.verify_node(
        MockRestMiddleware(eth_endpoint=MOCK_ETH_PROVIDER_URI).client
    )

    globalLogPublisher.addObserver(warning_trapper)
    vladimir.network_middleware.propagate_shitty_interface_id(other_ursula, vladimir.metadata())
    globalLogPublisher.removeObserver(warning_trapper)

    # So far, Ursula hasn't noticed any Vladimirs.
    assert len(warnings) == 0

    # ...but now, Ursula will now try to learn about Vladimir on a different thread.
    other_ursula.block_until_specific_nodes_are_known([vladimir.staking_provider_address])
    vladimir_as_learned = other_ursula.peers[vladimir.staking_provider_address]

    # OK, so cool, let's see what happens when Ursula tries to learn with Vlad as the peer.
    other_ursula._current_peer = vladimir_as_learned

    globalLogPublisher.addObserver(warning_trapper)
    other_ursula.learn_from_peer()
    globalLogPublisher.removeObserver(warning_trapper)

    # Indeed, Ursula noticed that something was up.
    assert len(warnings) == 1
    warning = warnings[0]['log_format']
    assert "Peer " + str(vladimir_as_learned.checksum_address) + " is invalid" in warning
    assert "Metadata signature is invalid" in warning

    # TODO (#567)
    # ...and booted him from peers
    # assert vladimir not in other_ursula.peers


@pytest.mark.usefixtures("monkeypatch_get_staking_provider_from_operator")
def test_alice_refuses_to_select_node_unless_ursula_is_valid(
    alice, idle_policy, ursulas
):
    Vladimir.network_middleware = EvilMiddleWare(eth_endpoint=MOCK_ETH_PROVIDER_URI)
    target = list(ursulas)[2]
    # First, let's imagine that Alice has sampled a Vladimir while making this policy.
    vladimir = Vladimir.from_target_ursula(target,
                                           substitute_verifying_key=True,
                                           sign_metadata=True)

    # Ideally, a fishy node will be present in `peers`,
    # This tests the case when it became fishy after discovering it
    # but before being selected for a policy.
    alice.peers.record_node(vladimir)
    alice.peers.record_fleet_state()

    # unmock the ping endpoint on mock rest middleware for this test.
    MockRestMiddleware.ping = RestMiddleware.ping

    with pytest.raises(vladimir.InvalidNode):
        idle_policy._ping_node(
            address=vladimir.checksum_address,
            network_middleware=alice.network_middleware,
        )
