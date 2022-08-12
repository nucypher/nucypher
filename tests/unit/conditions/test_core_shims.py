import pytest

from nucypher.core import MessageKit


@pytest.mark.skip("Awaiting integration with nc core shims")
def test_conditional_message_kit_serialization(enacted_federated_policy, ERC1155_balance_condition):
    # Version 1.0
    plaintext = b'llamas without conditions'
    mk = MessageKit(
        plaintext=plaintext,
        policy_encrypting_key=enacted_federated_policy.public_key,
    )
    mk_bytes = bytes(mk)
    restored_mk = MessageKit.from_bytes(mk_bytes)
    assert restored_mk.lingos is None

    # Version 1.1
    plaintext = b'llamas with conditions'
    mk = MessageKit(
        plaintext=plaintext,
        policy_encrypting_key=enacted_federated_policy.public_key,
        decryption_condition=ERC1155_balance_condition,
    )
    mk_bytes = bytes(mk)
    restored_mk = MessageKit.from_bytes(mk_bytes)
    assert bytes(restored_mk.lingos) == bytes(ERC1155_balance_condition)
