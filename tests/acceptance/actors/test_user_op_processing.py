import os

import pytest
from eth_account import Account

from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.utilities.erc4337_utils import (
    AAVersion,
    PackedUserOperation,
    UserOperation,
)


@pytest.fixture(scope="module")
def transactor(initiator):
    return initiator


@pytest.fixture(scope="module")
def user_op(accounts, get_random_checksum_address):
    user_op = UserOperation(
        sender=accounts[0].address,
        nonce=0,
        factory=get_random_checksum_address(),
        factory_data=os.urandom(23),
        call_data=os.urandom(32),
        verification_gas_limit=100000,
        # these should all be unique values (for proper testing)
        call_gas_limit=100000,
        pre_verification_gas=21000,
        max_priority_fee_per_gas=1000000000,  # 1 gwei
        max_fee_per_gas=2000000000,  # 2 gwei
    )
    return user_op


def test_aa_version_v08_hashing(user_op, chain, aa_entry_point, transactor):
    packed_user_op = PackedUserOperation.from_user_operation(user_op)
    message_hash, signature = packed_user_op.sign(
        transactor.transacting_power, AAVersion.V08, chain.chain_id
    )

    packed_user_op_dict = packed_user_op.to_eip712_struct(
        AAVersion.V08, chain.chain_id
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


def test_aa_version_mdt_hashing(user_op, chain, aa_entry_point, transactor):
    packed_user_op = PackedUserOperation.from_user_operation(user_op)
    message_hash, signature = packed_user_op.sign(
        transactor.transacting_power, AAVersion.MDT, chain.chain_id
    )

    packed_user_op_dict = packed_user_op.to_eip712_struct(
        AAVersion.MDT, chain.chain_id
    )["message"]
    packed_user_op_dict["signature"] = b""

    # verify hash matches expected entry point hash
    expected_hash = aa_entry_point.getUserOpHashMDT(packed_user_op_dict)
    assert message_hash == expected_hash

    # signature is correct for calculated hash
    recovered_address = Account._recover_hash(
        message_hash=message_hash, signature=signature
    )
    assert recovered_address == transactor.transacting_power.account


def test_packed_user_operation_gas_limit_packing(chain, user_op, aa_entry_point):
    packed_user_op = PackedUserOperation.from_user_operation(user_op)

    packed_user_op_dict = packed_user_op.to_eip712_struct(
        AAVersion.V08, chain.chain_id
    )["message"]
    packed_user_op_dict["signature"] = b""

    # retrieved gas limits packed into accountGasLimits should match
    assert (
        aa_entry_point.verificationGasLimit(packed_user_op_dict)
        == user_op.verification_gas_limit
    )
    assert aa_entry_point.callGasLimit(packed_user_op_dict) == user_op.call_gas_limit


def test_packed_user_operation_gas_fees_packing(chain, user_op, aa_entry_point):
    packed_user_op = PackedUserOperation.from_user_operation(user_op)

    packed_user_op_dict = packed_user_op.to_eip712_struct(
        AAVersion.V08, chain.chain_id
    )["message"]
    packed_user_op_dict["signature"] = b""

    # retrieved individual gas fees packed into gasFees should match
    assert aa_entry_point.maxFeePerGas(packed_user_op_dict) == user_op.max_fee_per_gas
    assert (
        aa_entry_point.maxPriorityFeePerGas(packed_user_op_dict)
        == user_op.max_priority_fee_per_gas
    )


def test_packed_user_operation_paymaster_and_data_packing(
    accounts, chain, user_op, aa_entry_point
):
    paymaster = accounts[1].address

    user_op.paymaster = paymaster
    user_op.paymaster_post_op_gas_limit = 100000
    user_op.paymaster_verification_gas_limit = 200000
    user_op.paymaster_data = b"paymasterdata"

    packed_user_op = PackedUserOperation.from_user_operation(user_op)

    packed_user_op_dict = packed_user_op.to_eip712_struct(
        AAVersion.V08, chain.chain_id
    )["message"]
    packed_user_op_dict["signature"] = b""

    # retrieved individual paymaster values packed into paymaster should match
    assert aa_entry_point.paymaster(packed_user_op_dict) == paymaster
    assert (
        aa_entry_point.paymasterVerificationGasLimit(packed_user_op_dict)
        == user_op.paymaster_verification_gas_limit
    )
    assert (
        aa_entry_point.paymasterPostOpGasLimit(packed_user_op_dict)
        == user_op.paymaster_post_op_gas_limit
    )
    assert aa_entry_point.paymasterData(packed_user_op_dict) == user_op.paymaster_data


def test_packed_user_operation_init_code_packing(
    accounts, chain, user_op, aa_entry_point
):
    # retrieved individual factory values packed into factory should match
    packed_user_op = PackedUserOperation.from_user_operation(user_op)
    packed_user_op_dict = packed_user_op.to_eip712_struct(
        AAVersion.V08, chain.chain_id
    )["message"]
    packed_user_op_dict["signature"] = b""
    assert aa_entry_point.factory(packed_user_op_dict) == user_op.factory
    assert aa_entry_point.factoryData(packed_user_op_dict) == user_op.factory_data

    # factory with no data
    user_op.factory_data = b""
    packed_user_op = PackedUserOperation.from_user_operation(user_op)
    packed_user_op_dict = packed_user_op.to_eip712_struct(
        AAVersion.V08, chain.chain_id
    )["message"]
    packed_user_op_dict["signature"] = b""
    assert aa_entry_point.factory(packed_user_op_dict) == user_op.factory
    assert aa_entry_point.factoryData(packed_user_op_dict) == b""

    # retry with empty values
    user_op.factory = None
    user_op.factory_data = b""
    packed_user_op = PackedUserOperation.from_user_operation(user_op)
    packed_user_op_dict = packed_user_op.to_eip712_struct(
        AAVersion.V08, chain.chain_id
    )["message"]
    packed_user_op_dict["signature"] = b""
    assert aa_entry_point.factory(packed_user_op_dict) == NULL_ADDRESS
    assert aa_entry_point.factoryData(packed_user_op_dict) == b""
