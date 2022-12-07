import json

import pytest
from nucypher_core import Address, Conditions, RetrievalKit
from nucypher_core._nucypher_core import MessageKit

from tests.utils.middleware import NodeIsDownMiddleware
from tests.utils.policy import make_message_kits


def _policy_info_kwargs(enacted_policy):
    return dict(
        encrypted_treasure_map=enacted_policy.treasure_map,
        alice_verifying_key=enacted_policy.publisher_verifying_key,
        )


def test_retrieval_kit(enacted_blockchain_policy, blockchain_ursulas):
    messages, message_kits = make_message_kits(enacted_blockchain_policy.public_key)

    capsule = message_kits[0].capsule
    addresses = {
        Address(ursula.canonical_address) for ursula in list(blockchain_ursulas)[:2]
    }

    retrieval_kit = RetrievalKit(capsule, addresses, conditions=None)
    serialized = bytes(retrieval_kit)
    retrieval_kit_back = RetrievalKit.from_bytes(serialized)

    assert retrieval_kit.capsule == retrieval_kit_back.capsule
    assert retrieval_kit.queried_addresses == retrieval_kit_back.queried_addresses


def test_single_retrieve(enacted_blockchain_policy, blockchain_bob, blockchain_ursulas):
    blockchain_bob.remember_node(blockchain_ursulas[0])
    blockchain_bob.start_learning_loop()
    messages, message_kits = make_message_kits(enacted_blockchain_policy.public_key)

    cleartexts = blockchain_bob.retrieve_and_decrypt(
        message_kits=message_kits,
        **_policy_info_kwargs(enacted_blockchain_policy),
    )

    assert cleartexts == messages


def test_single_retrieve_conditions_set_directly_to_none(
    enacted_blockchain_policy, blockchain_bob, blockchain_ursulas
):
    blockchain_bob.start_learning_loop()
    message = b"plaintext1"

    # MessageKit is created directly in this test, to ensure consistency
    message_kit = MessageKit(
        policy_encrypting_key=enacted_blockchain_policy.public_key,
        plaintext=message,
        conditions=None,
    )
    cleartexts = blockchain_bob.retrieve_and_decrypt(
        message_kits=[message_kit],
        **_policy_info_kwargs(enacted_blockchain_policy),
    )
    assert cleartexts == [message]


def test_single_retrieve_conditions_empty_list(
    enacted_blockchain_policy, blockchain_bob, blockchain_ursulas
):
    blockchain_bob.start_learning_loop()
    message = b"plaintext1"

    # MessageKit is created directly in this test, to ensure consistency
    message_kit = MessageKit(
        policy_encrypting_key=enacted_blockchain_policy.public_key,
        plaintext=message,
        conditions=Conditions(json.dumps([])),
    )
    cleartexts = blockchain_bob.retrieve_and_decrypt(
        message_kits=[message_kit],
        **_policy_info_kwargs(enacted_blockchain_policy),
    )
    assert cleartexts == [message]


@pytest.mark.skip(
    "This test is not working yet.  It's not clear what the correct behavior is and if it's the same in nucypher-ts."
)
def test_use_external_cache(
    enacted_blockchain_policy, blockchain_bob, blockchain_ursulas
):

    blockchain_bob.start_learning_loop()
    messages, message_kits = make_message_kits(enacted_blockchain_policy.public_key)

    ursulas = list(blockchain_ursulas)

    # All Ursulas are down except for two
    blockchain_bob.network_middleware = NodeIsDownMiddleware()
    for ursula in ursulas[2:]:
        blockchain_bob.network_middleware.node_is_down(ursula)

    # Fetch what we can without decrypting
    loaded_message_kits = blockchain_bob.retrieve(
        message_kits=message_kits,
        **_policy_info_kwargs(enacted_blockchain_policy),
        )

    # Not enough cfrags yet
    assert not any(mk.is_decryptable_by_receiver() for mk in loaded_message_kits)

    # Now the remaining two Ursulas go down.
    for ursula in ursulas[:2]:
        blockchain_bob.network_middleware.node_is_down(ursula)

    # ...but one other comes up.
    blockchain_bob.network_middleware.node_is_up(ursulas[2])

    # Try again, building on top of the existing cache
    loaded_message_kits = blockchain_bob.retrieve(
        message_kits=loaded_message_kits,
        **_policy_info_kwargs(enacted_blockchain_policy),
        )

    assert all(mk.is_decryptable_by_receiver() for mk in loaded_message_kits)

    # Should be enough cfrags now. Disconnect all Ursulas
    # to be sure Bob doesn't cheat and contact them again.
    for ursula in ursulas:
        blockchain_bob.network_middleware.node_is_down(ursula)

    cleartexts = blockchain_bob.retrieve_and_decrypt(
        message_kits=loaded_message_kits,
        **_policy_info_kwargs(enacted_blockchain_policy),
        )

    assert cleartexts == messages
