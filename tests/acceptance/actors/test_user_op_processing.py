import os

import pytest
from eth_account import Account
from nucypher_core import (
    AAVersion,
    PackedUserOperation,
    UserOperation,
)

from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.utilities.erc4337_utils import sign_packed_user_operation


@pytest.fixture(scope="module")
def transactor(initiator):
    return initiator


@pytest.fixture(scope="module")
def user_op_args(accounts, get_random_checksum_address):
    large_nonce = int.from_bytes(os.urandom(32), byteorder="big")
    return dict(
        sender=accounts[0].address,
        nonce=large_nonce,  # create very large nonce
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


@pytest.fixture(scope="module")
def packed_user_op_args(accounts):
    large_nonce = int.from_bytes(os.urandom(32), byteorder="big")
    return dict(
        sender=accounts[0].address,
        nonce=large_nonce,
        init_code=os.urandom(32),
        call_data=os.urandom(32),
        account_gas_limits=os.urandom(16),
        pre_verification_gas=21000,
        gas_fees=os.urandom(16),
        paymaster_and_data=os.urandom(32),
    )


def create_user_op(user_op_args, **overrides):
    return UserOperation(**{**user_op_args, **overrides})


def test_aa_version_v08_hashing(chain, aa_entry_point, transactor, packed_user_op_args):
    packed_user_op = PackedUserOperation(**packed_user_op_args)
    message_hash, signature = sign_packed_user_operation(
        packed_user_op, transactor.transacting_power, AAVersion.V08, chain.chain_id
    )

    packed_user_op_dict = packed_user_op.to_eip712_struct(
        AAVersion.V08, chain.chain_id
    )["message"]
    packed_user_op_dict["signature"] = b""

    # verify hash matches expected entry point hash
    expected_hash = aa_entry_point.getUserOpHashV8(packed_user_op_dict)
    assert expected_hash == message_hash

    # check raw python values hashing; ensures nucypher-core -> nucypher value consistency
    raw_values = tuple([*packed_user_op_args.values(), b""])  # add empty signature
    raw_values_hash = aa_entry_point.getUserOpHashV8(raw_values)
    assert raw_values_hash == expected_hash

    # signature is correct for calculated hash
    recovered_address = Account._recover_hash(
        message_hash=message_hash, signature=signature
    )
    assert recovered_address == transactor.transacting_power.account


def test_aa_version_v07_hashing(chain, aa_entry_point, transactor, packed_user_op_args):
    packed_user_op = PackedUserOperation(**packed_user_op_args)
    message_hash, signature = sign_packed_user_operation(
        packed_user_op, transactor.transacting_power, AAVersion.V07, chain.chain_id
    )

    # verify hash matches expected entry point hash
    expected_hash = aa_entry_point.getUserOpHashV7(
        # send as struct tuple
        (
            packed_user_op.sender,
            packed_user_op.nonce,
            packed_user_op.init_code,
            packed_user_op.call_data,
            packed_user_op.account_gas_limits,
            packed_user_op.pre_verification_gas,
            packed_user_op.gas_fees,
            packed_user_op.paymaster_and_data,
            b"",  # signature
        )
    )
    assert expected_hash == message_hash


def test_aa_version_mdt_hashing(chain, aa_entry_point, transactor, packed_user_op_args):
    packed_user_op = PackedUserOperation(**packed_user_op_args)
    message_hash, signature = sign_packed_user_operation(
        packed_user_op, transactor.transacting_power, AAVersion.MDT, chain.chain_id
    )

    packed_user_op_dict = packed_user_op.to_eip712_struct(
        AAVersion.MDT, chain.chain_id
    )["message"]
    packed_user_op_dict["signature"] = b""

    # verify hash matches expected entry point hash
    expected_hash = aa_entry_point.getUserOpHashMDT(packed_user_op_dict)
    assert expected_hash == message_hash

    # check raw python values hashing; ensures nucypher-core -> nucypher value consistency
    raw_values = tuple([*packed_user_op_args.values(), b""])  # add empty signature
    raw_values_hash = aa_entry_point.getUserOpHashMDT(raw_values)
    assert raw_values_hash == expected_hash

    # signature is correct for calculated hash
    recovered_address = Account._recover_hash(
        message_hash=message_hash, signature=signature
    )
    assert recovered_address == transactor.transacting_power.account


def test_packed_user_operation_gas_limit_packing(chain, user_op_args, aa_entry_point):
    user_op = create_user_op(user_op_args)
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


def test_packed_user_operation_gas_fees_packing(chain, user_op_args, aa_entry_point):
    user_op = create_user_op(user_op_args)
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
    accounts, chain, user_op_args, aa_entry_point
):
    paymaster = accounts[1].address

    # with paymaster data
    overrides = dict(
        paymaster=paymaster,
        paymaster_post_op_gas_limit=100000,
        paymaster_verification_gas_limit=200000,
        paymaster_data=b"paymasterdata",
    )

    user_op = create_user_op(user_op_args, **overrides)
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


def test_packed_user_operation_paymaster_and_data_packing_without_paymaster_data(
    accounts, chain, user_op_args, aa_entry_point
):
    paymaster = accounts[1].address
    # without paymaster data
    overrides = dict(
        paymaster=paymaster,
        paymaster_post_op_gas_limit=100000,
        paymaster_verification_gas_limit=200000,
    )

    user_op = create_user_op(user_op_args, **overrides)
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
    assert aa_entry_point.paymasterData(packed_user_op_dict) == b""


def test_packed_user_operation_init_code_packing(
    accounts, chain, user_op_args, aa_entry_point
):
    user_op = create_user_op(user_op_args)
    # retrieved individual factory values packed into factory should match
    packed_user_op = PackedUserOperation.from_user_operation(user_op)
    packed_user_op_dict = packed_user_op.to_eip712_struct(
        AAVersion.V08, chain.chain_id
    )["message"]
    packed_user_op_dict["signature"] = b""
    assert aa_entry_point.factory(packed_user_op_dict) == user_op.factory
    assert aa_entry_point.factoryData(packed_user_op_dict) == user_op.factory_data

    # factory with no data
    user_op = create_user_op(user_op_args, factory_data=b"")
    packed_user_op = PackedUserOperation.from_user_operation(user_op)
    packed_user_op_dict = packed_user_op.to_eip712_struct(
        AAVersion.V08, chain.chain_id
    )["message"]
    packed_user_op_dict["signature"] = b""
    assert aa_entry_point.factory(packed_user_op_dict) == user_op.factory
    assert aa_entry_point.factoryData(packed_user_op_dict) == b""

    # retry with empty values
    user_op = create_user_op(user_op_args, factory=None, factory_data=b"")
    packed_user_op = PackedUserOperation.from_user_operation(user_op)
    packed_user_op_dict = packed_user_op.to_eip712_struct(
        AAVersion.V08, chain.chain_id
    )["message"]
    packed_user_op_dict["signature"] = b""
    assert aa_entry_point.factory(packed_user_op_dict) == NULL_ADDRESS
    assert aa_entry_point.factoryData(packed_user_op_dict) == b""
