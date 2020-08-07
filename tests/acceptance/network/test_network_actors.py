"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import datetime

import maya
import pytest
from hendrix.experience import crosstown_traffic
from hendrix.utils.test_utils import crosstownTaskListDecoratorFactory

from nucypher.acumen.nicknames import nickname_from_seed
from nucypher.acumen.perception import FleetSensor
from nucypher.characters.unlawful import Vladimir
from nucypher.crypto.powers import SigningPower
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD
from tests.utils.middleware import MockRestMiddleware


@pytest.mark.slow()
def test_all_blockchain_ursulas_know_about_all_other_ursulas(blockchain_ursulas, agency):
    """
    Once launched, all Ursulas know about - and can help locate - all other Ursulas in the network.
    """
    token_agent, staking_agent, policy_agent = agency
    for address in staking_agent.swarm():
        for propagating_ursula in blockchain_ursulas[:1]:  # Last Ursula is not staking
            if address == propagating_ursula.checksum_address:
                continue
            else:
                assert address in propagating_ursula.known_nodes.addresses(), "{} did not know about {}". \
                    format(propagating_ursula, nickname_from_seed(address))


@pytest.mark.slow()
def test_blockchain_alice_finds_ursula_via_rest(blockchain_alice, blockchain_ursulas):
    # Imagine alice knows of nobody.
    blockchain_alice._Learner__known_nodes = FleetSensor()

    blockchain_alice.remember_node(blockchain_ursulas[0])
    blockchain_alice.learn_from_teacher_node()
    assert len(blockchain_alice.known_nodes) == len(blockchain_ursulas)

    for ursula in blockchain_ursulas:
        assert ursula in blockchain_alice.known_nodes


def test_treasure_map_cannot_be_duplicated(blockchain_ursulas, blockchain_alice, blockchain_bob, agency):

    # Setup the policy details
    n = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Create the Policy, Granting access to Bob
    policy = blockchain_alice.grant(bob=blockchain_bob,
                                    label=label,
                                    m=2,
                                    n=n,
                                    rate=int(1e18),  # one ether
                                    expiration=policy_end_datetime)

    u = blockchain_bob.matching_nodes_among(blockchain_alice.known_nodes)[0]
    saved_map = u.treasure_maps[bytes.fromhex(policy.treasure_map.public_id())]
    assert saved_map == policy.treasure_map
    # This Ursula was actually a Vladimir.
    # Thus, he has access to the (encrypted) TreasureMap and can use its details to
    # try to store his own fake details.
    vladimir = Vladimir.from_target_ursula(u)
    node_on_which_to_store_bad_map = blockchain_ursulas[1]
    with pytest.raises(vladimir.network_middleware.UnexpectedResponse) as e:
        vladimir.publish_fraudulent_treasure_map(legit_treasure_map=saved_map,
                                                 target_node=node_on_which_to_store_bad_map)
    assert e.value.status == 402


@pytest.mark.skip("See Issue #1075")  # TODO: Issue #1075
def test_vladimir_illegal_interface_key_does_not_propagate(blockchain_ursulas):
    """
    Although Ursulas propagate each other's interface information, as demonstrated above,
    they do not propagate interface information for Vladimir.

    Specifically, if Vladimir tries to perform the most obvious imitation attack -
    propagating his own wallet address along with Ursula's information - the validity
    check will catch it and Ursula will refuse to propagate it and also record Vladimir's
    details.
    """
    ursulas = list(blockchain_ursulas)
    ursula_whom_vladimir_will_imitate, other_ursula = ursulas[0], ursulas[1]

    # Vladimir sees Ursula on the network and tries to use her public information.
    vladimir = Vladimir.from_target_ursula(ursula_whom_vladimir_will_imitate)

    # This Ursula is totally legit...
    ursula_whom_vladimir_will_imitate.verify_node(MockRestMiddleware(), accept_federated_only=True)

    learning_callers = []
    crosstown_traffic.decorator = crosstownTaskListDecoratorFactory(learning_callers)

    vladimir.network_middleware.propagate_shitty_interface_id(other_ursula, bytes(vladimir))

    # So far, Ursula hasn't noticed any Vladimirs.
    assert other_ursula.suspicious_activities_witnessed['vladimirs'] == []

    # ...but now, Ursula will now try to learn about Vladimir on a different thread.
    # We only passed one node (Vladimir)...
    learn_about_vladimir = learning_callers.pop()
    #  ...so there was only one learning caller in the queue (now none since we popped it just now).
    assert len(learning_callers) == 0

    # OK, so cool, let's see what happens when Ursula tries to learn about Vlad.
    learn_about_vladimir()

    # And indeed, Ursula noticed the situation.
    # She didn't record Vladimir's address.
    assert vladimir not in other_ursula.known_nodes

    # But she *did* record the actual Ursula's address.
    assert ursula_whom_vladimir_will_imitate in other_ursula.known_nodes

    # Furthermore, she properly marked Vladimir as suspicious.
    assert vladimir in other_ursula.suspicious_activities_witnessed['vladimirs']


@pytest.mark.skip("See Issue #1075")  # TODO: Issue #1075
def test_alice_refuses_to_make_arrangement_unless_ursula_is_valid(blockchain_alice,
                                                                  idle_blockchain_policy,
                                                                  blockchain_ursulas):
    target = list(blockchain_ursulas)[2]
    # First, let's imagine that Alice has sampled a Vladimir while making this policy.
    vladimir = Vladimir.from_target_ursula(target)

    message = vladimir._signable_interface_info_message()
    signature = vladimir._crypto_power.power_ups(SigningPower).sign(message)

    vladimir.substantiate_stamp(client_password=INSECURE_DEVELOPMENT_PASSWORD)
    vladimir._Teacher__interface_signature = signature

    class FakeArrangement:
        federated = False
        ursula = target

    vladimir.node_storage.store_node_certificate(certificate=target.certificate)

    with pytest.raises(vladimir.InvalidNode):
        idle_blockchain_policy.propose_arrangement(network_middleware=blockchain_alice.network_middleware,
                                                   arrangement=FakeArrangement(),
                                                   ursula=vladimir)


@pytest.mark.skip('Needs to be restored -- no way to access treasure maps from stranger ursulas here.')
def test_treasure_map_cannot_be_duplicated(blockchain_ursulas, blockchain_alice, blockchain_bob, agency):

    # Setup the policy details
    n = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Create the Policy, Granting access to Bob
    policy = blockchain_alice.grant(bob=blockchain_bob,
                                    label=label,
                                    m=2,
                                    n=n,
                                    rate=int(1e18),  # one ether
                                    expiration=policy_end_datetime)

    u = blockchain_bob.matching_nodes_among(blockchain_alice.known_nodes)[0]
    saved_map = u._stored_treasure_maps[bytes.fromhex(policy.treasure_map.public_id())]
    assert saved_map == policy.treasure_map
    # This Ursula was actually a Vladimir.
    # Thus, he has access to the (encrypted) TreasureMap and can use its details to
    # try to store his own fake details.
    vladimir = Vladimir.from_target_ursula(u)
    node_on_which_to_store_bad_map = blockchain_ursulas[1]
    with pytest.raises(vladimir.network_middleware.UnexpectedResponse) as e:
        vladimir.publish_fraudulent_treasure_map(legit_treasure_map=saved_map,
                                                 target_node=node_on_which_to_store_bad_map)
    assert e.value.status == 402
