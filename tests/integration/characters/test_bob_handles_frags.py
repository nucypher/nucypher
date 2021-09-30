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

import pytest
import pytest_twisted
from twisted.internet import threads

from nucypher.core import RetrievalKit

from nucypher.characters.lawful import Enrico, Bob
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.network.retrieval import RetrievalClient

from tests.utils.middleware import MockRestMiddleware, NodeIsDownMiddleware


def _policy_info_kwargs(enacted_policy):
    return dict(
        encrypted_treasure_map=enacted_policy.treasure_map,
        alice_verifying_key=enacted_policy.publisher_verifying_key,
        )


def _make_message_kits(policy_pubkey):
    messages = [b"plaintext1", b"plaintext2", b"plaintext3"]

    message_kits = []
    for message in messages:
        # Using different Enricos, because why not.
        enrico = Enrico(policy_encrypting_key=policy_pubkey)
        message_kit = enrico.encrypt_message(message)
        message_kits.append(message_kit)

    return messages, message_kits


def test_retrieval_kit(enacted_federated_policy, federated_ursulas):
    messages, message_kits = _make_message_kits(enacted_federated_policy.public_key)

    capsule = message_kits[0].capsule
    addresses = [ursula.checksum_address for ursula in list(federated_ursulas)[:2]]

    retrieval_kit = RetrievalKit(capsule, addresses)
    serialized = bytes(retrieval_kit)
    retrieval_kit_back = RetrievalKit.from_bytes(serialized)

    assert retrieval_kit.capsule == retrieval_kit_back.capsule
    assert retrieval_kit.queried_addresses == retrieval_kit_back.queried_addresses


def test_single_retrieve(enacted_federated_policy, federated_bob, federated_ursulas):

    federated_bob.start_learning_loop()
    messages, message_kits = _make_message_kits(enacted_federated_policy.public_key)

    cleartexts = federated_bob.retrieve_and_decrypt(
        message_kits=message_kits,
        **_policy_info_kwargs(enacted_federated_policy),
        )

    assert cleartexts == messages


def test_use_external_cache(enacted_federated_policy, federated_bob, federated_ursulas):

    federated_bob.start_learning_loop()
    messages, message_kits = _make_message_kits(enacted_federated_policy.public_key)

    ursulas = list(federated_ursulas)

    # All Ursulas are down except for two
    federated_bob.network_middleware = NodeIsDownMiddleware()
    for ursula in ursulas[2:]:
        federated_bob.network_middleware.node_is_down(ursula)

    # Fetch what we can without decrypting
    loaded_message_kits = federated_bob.retrieve(
        message_kits=message_kits,
        **_policy_info_kwargs(enacted_federated_policy),
        )

    # Not enough cfrags yet
    assert not any(mk.is_decryptable_by_receiver() for mk in loaded_message_kits)

    # Now the remaining two Ursulas go down.
    for ursula in ursulas[:2]:
        federated_bob.network_middleware.node_is_down(ursula)

    # ...but one other comes up.
    federated_bob.network_middleware.node_is_up(ursulas[2])

    # Try again, building on top of the existing cache
    loaded_message_kits = federated_bob.retrieve(
        message_kits=loaded_message_kits,
        **_policy_info_kwargs(enacted_federated_policy),
        )

    assert all(mk.is_decryptable_by_receiver() for mk in loaded_message_kits)

    # Should be enough cfrags now. Disconnect all Ursulas
    # to be sure Bob doesn't cheat and contact them again.
    for ursula in ursulas:
        federated_bob.network_middleware.node_is_down(ursula)

    cleartexts = federated_bob.retrieve_and_decrypt(
        message_kits=loaded_message_kits,
        **_policy_info_kwargs(enacted_federated_policy),
        )

    assert cleartexts == messages
