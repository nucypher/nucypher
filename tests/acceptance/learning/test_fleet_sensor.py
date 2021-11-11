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
from requests.exceptions import SSLError

from nucypher.acumen.perception import FleetSensor
from nucypher.config.constants import TEMPORARY_DOMAIN
from constant_sorrow.constants import UNVERIFIED, VERIFIED, SUSPICIOUS, UNAVAILABLE, INVALID, UNBONDED, UNSTAKED

from nucypher.core import MetadataResponse
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.nodes import Teacher


def test_nodes_initially_labelled_unverified(blockchain_alice, blockchain_ursulas):
    # Imagine alice knows of nobody.
    blockchain_alice._Learner__known_nodes = FleetSensor(domain=TEMPORARY_DOMAIN)
    assert len(blockchain_alice.known_nodes) == 0

    blockchain_alice.remember_node(blockchain_ursulas[0])
    blockchain_alice.learn_from_teacher_node()
    assert len(blockchain_alice.known_nodes) == len(blockchain_ursulas)

    for ursula in blockchain_ursulas:
        assert ursula in blockchain_alice.known_nodes
        # ursulas labelled appropriately
        assert blockchain_alice.known_nodes.get_label(ursula.checksum_address) == UNVERIFIED


def test_verification_of_node_changes_label_to_verified(blockchain_alice, blockchain_ursulas):
    # Imagine alice knows of nobody.
    blockchain_alice._Learner__known_nodes = FleetSensor(domain=TEMPORARY_DOMAIN)
    assert len(blockchain_alice.known_nodes) == 0

    initial_teacher_ursula, *others = list(blockchain_ursulas)
    blockchain_alice.remember_node(initial_teacher_ursula, eager=True)  # verify initial_teacher
    assert initial_teacher_ursula in blockchain_alice.known_nodes
    assert blockchain_alice.known_nodes.get_label(initial_teacher_ursula.checksum_address) == VERIFIED

    blockchain_alice.learn_from_teacher_node(eager=True)
    assert len(blockchain_alice.known_nodes) == len(blockchain_ursulas)
    for ursula in others:
        # other ursulas are known and marked as unverified
        assert ursula in blockchain_alice.known_nodes
        assert blockchain_alice.known_nodes.get_label(ursula.checksum_address) == VERIFIED


def test_teacher_with_badly_signed_known_nodes_labelled_suspicious(blockchain_alice, blockchain_ursulas, mocker):
    # Imagine alice knows of nobody.
    blockchain_alice._Learner__known_nodes = FleetSensor(domain=TEMPORARY_DOMAIN)
    assert len(blockchain_alice.known_nodes) == 0

    blockchain_teacher = blockchain_ursulas[0]
    blockchain_alice.remember_node(blockchain_teacher)

    def bad_bytestring_of_known_nodes():
        # Signing with the learner's signer instead of the teacher's signer
        response = MetadataResponse.author(signer=blockchain_alice.stamp.as_umbral_signer(),
                                           timestamp_epoch=blockchain_teacher.known_nodes.timestamp.epoch)
        return bytes(response)

    mocker.patch.object(blockchain_teacher, 'bytestring_of_known_nodes', bad_bytestring_of_known_nodes)
    blockchain_alice._current_teacher_node = blockchain_teacher
    blockchain_alice.learn_from_teacher_node(eager=True)

    assert blockchain_alice.known_nodes.get_label(blockchain_teacher.checksum_address) == SUSPICIOUS


def test_teacher_invalid_node_exception_labelled_invalid(blockchain_alice, blockchain_ursulas, mocker):
    # Imagine alice knows of nobody.
    blockchain_alice._Learner__known_nodes = FleetSensor(domain=TEMPORARY_DOMAIN)
    assert len(blockchain_alice.known_nodes) == 0

    blockchain_teacher = blockchain_ursulas[0]

    # issue with teacher when trying ot learn from it
    mocker.patch.object(blockchain_alice.network_middleware, 'get_nodes_via_rest', side_effect=Teacher.InvalidNode)
    blockchain_alice.remember_node(blockchain_teacher)
    blockchain_alice._current_teacher_node = blockchain_teacher
    blockchain_alice.learn_from_teacher_node(eager=True)
    assert blockchain_alice.known_nodes.get_label(blockchain_teacher.checksum_address) == INVALID


def test_teacher_down_labelled_unavailable(blockchain_alice, blockchain_ursulas, mocker):
    # Imagine alice knows of nobody.
    blockchain_alice._Learner__known_nodes = FleetSensor(domain=TEMPORARY_DOMAIN)
    assert len(blockchain_alice.known_nodes) == 0

    blockchain_teacher = blockchain_ursulas[0]

    # issue with teacher when trying ot learn from it
    mocker.patch.object(blockchain_alice.network_middleware, 'get_nodes_via_rest', side_effect=NodeSeemsToBeDown)
    blockchain_alice.remember_node(blockchain_teacher)
    blockchain_alice._current_teacher_node = blockchain_teacher
    blockchain_alice.learn_from_teacher_node(eager=True)
    assert blockchain_alice.known_nodes.get_label(blockchain_teacher.checksum_address) == UNAVAILABLE


def test_node_ssl_error_labelled_suspicious(blockchain_alice, blockchain_ursulas, mocker):
    # Imagine alice knows of nobody.
    blockchain_alice._Learner__known_nodes = FleetSensor(domain=TEMPORARY_DOMAIN)
    assert len(blockchain_alice.known_nodes) == 0

    ursula = blockchain_ursulas[0]

    # issue when verifying a specific node
    mocker.patch.object(ursula, 'verify_node', side_effect=SSLError)
    blockchain_alice.remember_node(ursula, eager=True)
    assert blockchain_alice.known_nodes.get_label(ursula.checksum_address) == SUSPICIOUS


def test_node_down_labelled_unavailable(blockchain_alice, blockchain_ursulas, mocker):
    # Imagine alice knows of nobody.
    blockchain_alice._Learner__known_nodes = FleetSensor(domain=TEMPORARY_DOMAIN)
    assert len(blockchain_alice.known_nodes) == 0

    ursula = blockchain_ursulas[0]

    # issue when verifying a specific node
    mocker.patch.object(blockchain_alice.network_middleware.client, 'node_information', side_effect=NodeSeemsToBeDown)
    blockchain_alice.remember_node(ursula, eager=True, force_verification_recheck=True)
    assert blockchain_alice.known_nodes.get_label(ursula.checksum_address) == UNAVAILABLE


def test_node_not_staking_labelled_unstaked(blockchain_alice, blockchain_ursulas, mocker):
    # Imagine alice knows of nobody.
    blockchain_alice._Learner__known_nodes = FleetSensor(domain=TEMPORARY_DOMAIN)
    assert len(blockchain_alice.known_nodes) == 0

    ursula = blockchain_ursulas[0]

    # issue when verifying a specific node
    mocker.patch.object(ursula, '_staker_is_really_staking', return_value=False)
    blockchain_alice.remember_node(ursula, eager=True, force_verification_recheck=True)
    assert blockchain_alice.known_nodes.get_label(ursula.checksum_address) == UNSTAKED


def test_node_unbonded_labelled_unbonded(blockchain_alice, blockchain_ursulas, mocker):
    # Imagine alice knows of nobody.
    blockchain_alice._Learner__known_nodes = FleetSensor(domain=TEMPORARY_DOMAIN)
    assert len(blockchain_alice.known_nodes) == 0

    ursula = blockchain_ursulas[0]

    # issue when verifying a specific node
    mocker.patch.object(ursula, '_worker_is_bonded_to_staker', return_value=False)
    blockchain_alice.remember_node(ursula, eager=True, force_verification_recheck=True)
    assert blockchain_alice.known_nodes.get_label(ursula.checksum_address) == UNBONDED
