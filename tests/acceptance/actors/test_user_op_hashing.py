import pytest
from eth_account import Account

from nucypher.utilities.erc4337_utils import (
    EntryPointContracts,
    EntryPointVersion,
    PackedUserOperation,
    UserOperation,
)


@pytest.fixture
def mock_entry_point_contract_address(monkeypatch, aa_entry_point):
    # entry point contract uses its own address (not the canonical one) for domain so patch
    # needed to adjust address used for domain when signing UserOperation eip712 message
    monkeypatch.setattr(EntryPointContracts, "ENTRYPOINT_V08", aa_entry_point.address)


@pytest.fixture(scope="module")
def transactor(initiator):
    return initiator


def test_entry_point_v08_hashing(
    accounts, chain, aa_entry_point, transactor, mock_entry_point_contract_address
):
    user_op = UserOperation(
        sender=accounts[0].address,
        nonce=0,
        call_data=b"deadbeef",
        verification_gas_limit=100000,
        call_gas_limit=100000,
        pre_verification_gas=21000,
        max_priority_fee_per_gas=1000000000,  # 1 gwei
        max_fee_per_gas=2000000000,  # 2 gwei
    )

    packed_user_op = PackedUserOperation.from_user_operation(user_op)
    message_hash, signature = packed_user_op.sign(
        transactor.transacting_power, EntryPointVersion.V08, chain.chain_id
    )

    packed_user_op_dict = packed_user_op.to_eip712_struct(
        EntryPointVersion.V08, chain.chain_id
    )["message"]
    packed_user_op_dict["signature"] = b""

    # verify hash matches expected entry point hash
    expected_hash = aa_entry_point.getUserOpHashV8(packed_user_op_dict)
    assert message_hash == expected_hash

    # signature is correct for calculated hash
    recovered_address = Account._recover_hash(
        message_hash=message_hash, signature=signature
    )
    assert recovered_address == transactor.transacting_power.account
