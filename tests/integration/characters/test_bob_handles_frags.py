import json

from nucypher_core import Address, Conditions, RetrievalKit
from nucypher_core._nucypher_core import MessageKit

from tests.utils.middleware import NodeIsDownMiddleware
from tests.utils.policy import make_message_kits


def _policy_info_kwargs(enacted_policy):
    return dict(
        encrypted_treasure_map=enacted_policy.treasure_map,
        alice_verifying_key=enacted_policy.publisher_verifying_key,
        )


def test_retrieval_kit(enacted_federated_policy, federated_ursulas):
    messages, message_kits = make_message_kits(enacted_federated_policy.public_key)

    capsule = message_kits[0].capsule
    addresses = {Address(ursula.canonical_address) for ursula in list(federated_ursulas)[:2]}

    retrieval_kit = RetrievalKit(capsule, addresses)
    serialized = bytes(retrieval_kit)
    retrieval_kit_back = RetrievalKit.from_bytes(serialized)

    assert retrieval_kit.capsule == retrieval_kit_back.capsule
    assert retrieval_kit.queried_addresses == retrieval_kit_back.queried_addresses


def test_single_retrieve(enacted_federated_policy, federated_bob, federated_ursulas):
    federated_bob.start_learning_loop()
    messages, message_kits = make_message_kits(enacted_federated_policy.public_key)

    cleartexts = federated_bob.retrieve_and_decrypt(
        message_kits=message_kits,
        **_policy_info_kwargs(enacted_federated_policy),
    )

    assert cleartexts == messages


def test_single_retrieve_conditions_set_directly_to_none(
    enacted_federated_policy, federated_bob, federated_ursulas
):
    federated_bob.start_learning_loop()
    message = b"plaintext1"

    # MessageKit is created directly in this test, to ensure consistency
    message_kit = MessageKit(
        policy_encrypting_key=enacted_federated_policy.public_key,
        plaintext=message,
        conditions=None,
    )
    cleartexts = federated_bob.retrieve_and_decrypt(
        message_kits=[message_kit],
        **_policy_info_kwargs(enacted_federated_policy),
    )
    assert cleartexts == [message]


def test_single_retrieve_conditions_empty_list(
    enacted_federated_policy, federated_bob, federated_ursulas
):
    federated_bob.start_learning_loop()
    message = b"plaintext1"

    # MessageKit is created directly in this test, to ensure consistency
    message_kit = MessageKit(
        policy_encrypting_key=enacted_federated_policy.public_key,
        plaintext=message,
        conditions=Conditions(json.dumps([])),
    )
    cleartexts = federated_bob.retrieve_and_decrypt(
        message_kits=[message_kit],
        **_policy_info_kwargs(enacted_federated_policy),
    )
    assert cleartexts == [message]


def test_use_external_cache(enacted_federated_policy, federated_bob, federated_ursulas):

    federated_bob.start_learning_loop()
    messages, message_kits = make_message_kits(enacted_federated_policy.public_key)

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
