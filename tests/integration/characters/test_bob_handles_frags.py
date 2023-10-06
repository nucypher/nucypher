import json

from nucypher_core import Address, Conditions, RetrievalKit
from nucypher_core._nucypher_core import MessageKit

from tests.constants import MOCK_ETH_PROVIDER_URI
from tests.utils.middleware import NodeIsDownMiddleware
from tests.utils.policy import make_message_kits


def _policy_info_kwargs(enacted_policy):
    return dict(
        encrypted_treasure_map=enacted_policy.treasure_map,
        alice_verifying_key=enacted_policy.publisher_verifying_key,
        )

def test_retrieval_kit(enacted_policy, ursulas):
    messages, message_kits = make_message_kits(enacted_policy.public_key)

    capsule = message_kits[0].capsule
    addresses = {Address(ursula.canonical_address) for ursula in list(ursulas)[:2]}

    retrieval_kit = RetrievalKit(capsule, addresses, conditions=None)
    serialized = bytes(retrieval_kit)
    retrieval_kit_back = RetrievalKit.from_bytes(serialized)

    assert retrieval_kit.capsule == retrieval_kit_back.capsule
    assert retrieval_kit.queried_addresses == retrieval_kit_back.queried_addresses


def test_single_retrieve(enacted_policy, bob, ursulas):
    bob.remember_node(ursulas[0])
    bob.start_learning_loop()
    messages, message_kits = make_message_kits(enacted_policy.public_key)

    cleartexts = bob.retrieve_and_decrypt(
        message_kits=message_kits,
        **_policy_info_kwargs(enacted_policy),
    )

    assert cleartexts == messages


def test_single_retrieve_conditions_set_directly_to_none(enacted_policy, bob, ursulas):
    bob.start_learning_loop()
    message = b"plaintext1"

    # MessageKit is created directly in this test, to ensure consistency
    message_kit = MessageKit(
        policy_encrypting_key=enacted_policy.public_key,
        plaintext=message,
        conditions=None,
    )
    cleartexts = bob.retrieve_and_decrypt(
        message_kits=[message_kit],
        **_policy_info_kwargs(enacted_policy),
    )
    assert cleartexts == [message]


def test_single_retrieve_conditions_empty_list(enacted_policy, bob, ursulas):
    bob.start_learning_loop()
    message = b"plaintext1"

    # MessageKit is created directly in this test, to ensure consistency
    message_kit = MessageKit(
        policy_encrypting_key=enacted_policy.public_key,
        plaintext=message,
        conditions=Conditions(json.dumps([])),
    )
    cleartexts = bob.retrieve_and_decrypt(
        message_kits=[message_kit],
        **_policy_info_kwargs(enacted_policy),
    )
    assert cleartexts == [message]


def test_use_external_cache(enacted_policy, bob, ursulas):

    bob.start_learning_loop()
    messages, message_kits = make_message_kits(enacted_policy.public_key)

    ursulas = list(ursulas)

    # All Ursulas are down except for two
    bob.network_middleware = NodeIsDownMiddleware(eth_endpoint=MOCK_ETH_PROVIDER_URI)
    for ursula in ursulas[2:]:
        bob.network_middleware.node_is_down(ursula)

    # Fetch what we can without decrypting
    loaded_message_kits = bob.retrieve(
        message_kits=message_kits,
        **_policy_info_kwargs(enacted_policy),
        )

    # Not enough cfrags yet
    assert not any(mk.is_decryptable_by_receiver() for mk in loaded_message_kits)

    # Now the remaining two Ursulas go down.
    for ursula in ursulas[:2]:
        bob.network_middleware.node_is_down(ursula)

    # ...but one other comes up.
    bob.network_middleware.node_is_up(ursulas[2])

    # Try again, building on top of the existing cache
    loaded_message_kits = bob.retrieve(
        message_kits=loaded_message_kits,
        **_policy_info_kwargs(enacted_policy),
        )

    assert all(mk.is_decryptable_by_receiver() for mk in loaded_message_kits)

    # Should be enough cfrags now. Disconnect all Ursulas
    # to be sure Bob doesn't cheat and contact them again.
    for ursula in ursulas:
        bob.network_middleware.node_is_down(ursula)

    cleartexts = bob.retrieve_and_decrypt(
        message_kits=loaded_message_kits,
        **_policy_info_kwargs(enacted_policy),
        )

    assert cleartexts == messages
