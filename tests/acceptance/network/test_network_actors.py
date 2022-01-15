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
from twisted.logger import LogLevel, globalLogPublisher

from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent
from nucypher.acumen.nicknames import Nickname
from nucypher.acumen.perception import FleetSensor
from nucypher.characters.unlawful import Vladimir
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import SigningPower
from tests.utils.middleware import MockRestMiddleware


def test_all_blockchain_ursulas_know_about_all_other_ursulas(blockchain_ursulas, agency, test_registry):
    """
    Once launched, all Ursulas know about - and can help locate - all other Ursulas in the network.
    """
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)

    for address in staking_agent.swarm():
        for propagating_ursula in blockchain_ursulas[:1]:  # Last Ursula is not staking
            if address == propagating_ursula.checksum_address:
                continue
            else:
                assert address in propagating_ursula.known_nodes.addresses(), "{} did not know about {}". \
                    format(propagating_ursula, Nickname.from_seed(address))


def test_blockchain_alice_finds_ursula_via_rest(blockchain_alice, blockchain_ursulas):
    # Imagine alice knows of nobody.
    blockchain_alice._Learner__known_nodes = FleetSensor(domain=TEMPORARY_DOMAIN)

    blockchain_alice.remember_node(blockchain_ursulas[0])
    blockchain_alice.learn_from_teacher_node()
    assert len(blockchain_alice.known_nodes) == len(blockchain_ursulas)

    for ursula in blockchain_ursulas:
        assert ursula in blockchain_alice.known_nodes


def test_vladimir_illegal_interface_key_does_not_propagate(blockchain_ursulas):
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


    ursulas = list(blockchain_ursulas)
    ursula_whom_vladimir_will_imitate, other_ursula = ursulas[0], ursulas[1]

    # Vladimir sees Ursula on the network and tries to use her public information.
    vladimir = Vladimir.from_target_ursula(ursula_whom_vladimir_will_imitate)

    # This Ursula is totally legit...
    ursula_whom_vladimir_will_imitate.verify_node(MockRestMiddleware())

    globalLogPublisher.addObserver(warning_trapper)
    vladimir.network_middleware.propagate_shitty_interface_id(other_ursula, vladimir.metadata())
    globalLogPublisher.removeObserver(warning_trapper)

    # So far, Ursula hasn't noticed any Vladimirs.
    assert len(warnings) == 0

    # ...but now, Ursula will now try to learn about Vladimir on a different thread.
    other_ursula.block_until_specific_nodes_are_known([vladimir.checksum_address])
    vladimir_as_learned = other_ursula.known_nodes[vladimir.checksum_address]

    # OK, so cool, let's see what happens when Ursula tries to learn with Vlad as the teacher.
    other_ursula._current_teacher_node = vladimir_as_learned

    globalLogPublisher.addObserver(warning_trapper)
    result = other_ursula.learn_from_teacher_node()
    globalLogPublisher.removeObserver(warning_trapper)

    # Indeed, Ursula noticed that something was up.
    assert len(warnings) == 1
    warning = warnings[0]['log_format']
    assert "Teacher " + str(vladimir_as_learned) + " is invalid" in warning
    assert "Metadata signature is invalid" in warning  # TODO: Cleanup logging templates

    # TODO (#567)
    # ...and booted him from known_nodes
    # assert vladimir not in other_ursula.known_nodes


def test_alice_refuses_to_select_node_unless_ursula_is_valid(blockchain_alice,
                                                             idle_blockchain_policy,
                                                             blockchain_ursulas):

    target = list(blockchain_ursulas)[2]
    # First, let's imagine that Alice has sampled a Vladimir while making this policy.
    vladimir = Vladimir.from_target_ursula(target,
                                           substitute_verifying_key=True,
                                           sign_metadata=True)

    vladimir.node_storage.store_node_certificate(certificate=target.certificate, port=vladimir.rest_interface.port)

    # Ideally, a fishy node will be present in `known_nodes`,
    # This tests the case when it became fishy after discovering it
    # but before being selected for a policy.
    blockchain_alice.known_nodes.record_node(vladimir)
    blockchain_alice.known_nodes.record_fleet_state()

    with pytest.raises(vladimir.InvalidNode):
        idle_blockchain_policy._ping_node(address=vladimir.checksum_address,
                                          network_middleware=blockchain_alice.network_middleware)
