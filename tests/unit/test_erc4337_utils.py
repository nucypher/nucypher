from unittest.mock import Mock

import pytest
from eth_abi import encode
from eth_account import Account
from eth_account.messages import _hash_eip191_message, encode_defunct, encode_typed_data
from eth_utils import keccak, to_bytes
from hexbytes import HexBytes
from nucypher_core import (
    AAVersion,
    PackedUserOperation,
    UserOperation,
)

from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.policy.conditions.utils import camel_case_to_snake
from nucypher.utilities.erc4337_utils import (
    sign_packed_user_operation,
)
from tests.utils.erc4337 import (
    COMMON_REQUIRED_USER_OP_GAS_VALUES,
    create_contract_call,
    create_erc20_approve,
    create_erc20_transfer,
    create_eth_transfer,
    encode_function_call,
)

ENTRYPOINT_V08 = "0x4337084D9E255Ff0702461CF8895CE9E3b5Ff108"
ENTRYPOINT_V07 = "0x0000000071727De22E5E9d8BAf0edAc6f37da032"
LARGEST_NONCE_VALUE = 2**256 - 1


def _expected_pack_account_gas_limits(
    call_gas_limit: int, verification_gas_limit: int
) -> bytes:
    combined = (verification_gas_limit << 128) | call_gas_limit
    return combined.to_bytes(32, byteorder="big")


def _expected_pack_gas_fees(max_fee_per_gas: int, max_priority_fee_per_gas) -> bytes:
    combined = (max_priority_fee_per_gas << 128) | max_fee_per_gas
    return combined.to_bytes(32, byteorder="big")


def _expected_pack_paymaster_and_data(
    paymaster: str,
    paymaster_verification_gas_limit: int,
    paymaster_post_op_gas_limit: int,
    paymaster_data: bytes,
) -> bytes:
    if not paymaster:
        return b""
    paymaster_bytes = to_bytes(hexstr=paymaster)
    verification_bytes = paymaster_verification_gas_limit.to_bytes(16, byteorder="big")
    post_op_bytes = paymaster_post_op_gas_limit.to_bytes(16, byteorder="big")
    return paymaster_bytes + verification_bytes + post_op_bytes + paymaster_data


def _expected_pack_init_code(factory: str, factory_data: bytes) -> bytes:
    if not factory:
        return b""

    factory_bytes = to_bytes(hexstr=factory)
    if not factory_bytes or factory_bytes == bytes(HexBytes(NULL_ADDRESS)):
        return b""

    return factory_bytes + factory_data


class TestPackedUserOperation:
    """Test suite for PackedUserOperation class"""

    @pytest.fixture
    def sample_user_op(self, get_random_checksum_address):
        """Create a sample PackedUserOperation for testing"""
        return UserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=LARGEST_NONCE_VALUE,
            factory="0x27BbA3872e3e00632A200C08F7CD9E999a36BA85",
            factory_data=b"\x12\x34",
            call_data=b"\x56\x78",
            verification_gas_limit=100000,
            call_gas_limit=200000,
            pre_verification_gas=21000,
            max_priority_fee_per_gas=1000000000,  # 1 gwei
            max_fee_per_gas=2000000000,  # 2 gwei
            paymaster="0x9876543210987654321098765432109876543210",
            paymaster_verification_gas_limit=50000,
            paymaster_post_op_gas_limit=30000,
            paymaster_data=b"My whole life is consistent - SGA",
        )

    @pytest.fixture
    def minimal_user_op(self):
        """Create a minimal PackedUserOperation for testing"""
        return UserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=LARGEST_NONCE_VALUE,
            call_data=b"",
            **COMMON_REQUIRED_USER_OP_GAS_VALUES,
        )

    def test_user_operation_initialization(self, sample_user_op):
        """Test PackedUserOperation initialization with all fields"""
        assert sample_user_op.sender == "0x1234567890123456789012345678901234567890"
        assert sample_user_op.nonce == LARGEST_NONCE_VALUE
        assert sample_user_op.factory == "0x27BbA3872e3e00632A200C08F7CD9E999a36BA85"
        assert sample_user_op.factory_data == b"\x12\x34"
        assert sample_user_op.call_data == b"\x56\x78"
        assert sample_user_op.verification_gas_limit == 100000
        assert sample_user_op.call_gas_limit == 200000
        assert sample_user_op.pre_verification_gas == 21000
        assert sample_user_op.max_priority_fee_per_gas == 1000000000
        assert sample_user_op.max_fee_per_gas == 2000000000
        assert sample_user_op.paymaster == "0x9876543210987654321098765432109876543210"
        assert sample_user_op.paymaster_verification_gas_limit == 50000
        assert sample_user_op.paymaster_post_op_gas_limit == 30000
        assert sample_user_op.paymaster_data == b"My whole life is consistent - SGA"

    def test_minimal_user_operation_initialization(self, minimal_user_op):
        """Test PackedUserOperation initialization with minimal fields"""
        assert minimal_user_op.sender == "0x1234567890123456789012345678901234567890"
        assert minimal_user_op.nonce == LARGEST_NONCE_VALUE
        assert minimal_user_op.call_data == b""
        assert (
            minimal_user_op.verification_gas_limit
            == COMMON_REQUIRED_USER_OP_GAS_VALUES["verification_gas_limit"]
        )
        assert (
            minimal_user_op.call_gas_limit
            == COMMON_REQUIRED_USER_OP_GAS_VALUES["call_gas_limit"]
        )
        assert (
            minimal_user_op.pre_verification_gas
            == COMMON_REQUIRED_USER_OP_GAS_VALUES["pre_verification_gas"]
        )
        assert (
            minimal_user_op.max_priority_fee_per_gas
            == COMMON_REQUIRED_USER_OP_GAS_VALUES["max_priority_fee_per_gas"]
        )
        assert (
            minimal_user_op.max_fee_per_gas
            == COMMON_REQUIRED_USER_OP_GAS_VALUES["max_fee_per_gas"]
        )

        # optional fields
        assert minimal_user_op.factory is None
        assert minimal_user_op.factory_data is None
        assert minimal_user_op.paymaster is None
        assert minimal_user_op.paymaster_verification_gas_limit is None
        assert minimal_user_op.paymaster_post_op_gas_limit is None
        assert minimal_user_op.paymaster_data is None

    def test_serialization(self, sample_user_op, minimal_user_op):
        for user_op in [sample_user_op, minimal_user_op]:
            serialized_bytes = bytes(user_op)
            deserialized_op = UserOperation.from_bytes(serialized_bytes)

            assert deserialized_op.sender == user_op.sender
            assert deserialized_op.nonce == user_op.nonce
            assert deserialized_op.factory == user_op.factory
            assert deserialized_op.factory_data == user_op.factory_data
            assert deserialized_op.call_data == user_op.call_data
            assert (
                deserialized_op.verification_gas_limit == user_op.verification_gas_limit
            )
            assert deserialized_op.call_gas_limit == user_op.call_gas_limit
            assert deserialized_op.pre_verification_gas == user_op.pre_verification_gas
            assert (
                deserialized_op.max_priority_fee_per_gas
                == user_op.max_priority_fee_per_gas
            )
            assert deserialized_op.max_fee_per_gas == user_op.max_fee_per_gas
            assert deserialized_op.paymaster == user_op.paymaster
            assert (
                deserialized_op.paymaster_verification_gas_limit
                == user_op.paymaster_verification_gas_limit
            )
            assert (
                deserialized_op.paymaster_post_op_gas_limit
                == user_op.paymaster_post_op_gas_limit
            )

            assert bytes(user_op) == bytes(deserialized_op)

    def test_packed_user_op_serialization(self, sample_user_op, minimal_user_op):
        for user_op in [sample_user_op, minimal_user_op]:
            packed_user_op = PackedUserOperation.from_user_operation(user_op)
            serialized_bytes = bytes(packed_user_op)
            deserialized_op = PackedUserOperation.from_bytes(serialized_bytes)

            assert deserialized_op.sender == packed_user_op.sender
            assert deserialized_op.nonce == packed_user_op.nonce
            assert deserialized_op.init_code == packed_user_op.init_code
            assert deserialized_op.call_data == packed_user_op.call_data
            assert (
                deserialized_op.pre_verification_gas
                == packed_user_op.pre_verification_gas
            )
            assert deserialized_op.gas_fees == packed_user_op.gas_fees
            assert (
                deserialized_op.paymaster_and_data == packed_user_op.paymaster_and_data
            )

            assert bytes(packed_user_op) == bytes(deserialized_op)
            assert bytes(packed_user_op) != bytes(user_op)

    def test_packed_user_op_account_gas_limits(self, sample_user_op):
        """Test _pack_account_gas_limits method"""
        packed_user_op = PackedUserOperation.from_user_operation(sample_user_op)

        # Should be 32 bytes
        assert len(packed_user_op.account_gas_limits) == 32

        # Verify the packing: verification_gas_limit (16 bytes) + call_gas_limit (16 bytes)
        expected = (
            sample_user_op.verification_gas_limit << 128
        ) | sample_user_op.call_gas_limit
        assert packed_user_op.account_gas_limits == expected.to_bytes(
            32, byteorder="big"
        )

    def test_packed_user_op_fees(self, sample_user_op):
        """Test _pack_gas_fees method"""
        packed_user_op = PackedUserOperation.from_user_operation(sample_user_op)

        # Should be 32 bytes
        assert len(packed_user_op.gas_fees) == 32

        # Verify the packing: max_priority_fee_per_gas (16 bytes) + max_fee_per_gas (16 bytes)
        expected = (
            sample_user_op.max_priority_fee_per_gas << 128
        ) | sample_user_op.max_fee_per_gas
        assert packed_user_op.gas_fees == expected.to_bytes(32, byteorder="big")

    def test_get_init_code(
        self, get_random_checksum_address, sample_user_op, minimal_user_op
    ):
        # from sample user op
        packed_user_op = PackedUserOperation.from_user_operation(sample_user_op)
        assert (
            packed_user_op.init_code
            == bytes(HexBytes(sample_user_op.factory)) + sample_user_op.factory_data
        )

        # from minimal user op
        packed_user_op = PackedUserOperation.from_user_operation(minimal_user_op)
        assert packed_user_op.init_code == b""

    def test_packed_user_op_methods(self, sample_user_op):
        """Test the pack method returns correct dictionary structure"""
        packed_user_op = PackedUserOperation.from_user_operation(sample_user_op)

        # Verify types and values
        assert packed_user_op.sender == sample_user_op.sender
        assert packed_user_op.nonce == sample_user_op.nonce
        assert packed_user_op.init_code == (
            bytes(HexBytes(sample_user_op.factory)) + sample_user_op.factory_data
        )
        assert packed_user_op.call_data == sample_user_op.call_data
        assert (
            packed_user_op.pre_verification_gas == sample_user_op.pre_verification_gas
        )

        # Verify packed fields
        assert packed_user_op.account_gas_limits == _expected_pack_account_gas_limits(
            sample_user_op.call_gas_limit, sample_user_op.verification_gas_limit
        )
        assert packed_user_op.gas_fees == _expected_pack_gas_fees(
            sample_user_op.max_fee_per_gas, sample_user_op.max_priority_fee_per_gas
        )
        assert packed_user_op.paymaster_and_data == _expected_pack_paymaster_and_data(
            sample_user_op.paymaster,
            sample_user_op.paymaster_verification_gas_limit,
            sample_user_op.paymaster_post_op_gas_limit,
            sample_user_op.paymaster_data,
        )
        assert packed_user_op.init_code == _expected_pack_init_code(
            sample_user_op.factory, sample_user_op.factory_data
        )

    @pytest.mark.parametrize(
        "aa_version", [AAVersion.V07, AAVersion.V08, AAVersion.MDT]
    )
    def test_to_eip712_struct(self, aa_version, sample_user_op):
        """Test EIP-712 struct generation"""
        packed_user_op = PackedUserOperation.from_user_operation(sample_user_op)
        chain_id = 1

        if aa_version == AAVersion.V07:
            # try with aa version v07 which is invalid
            with pytest.raises(ValueError, match="Not supported for AA v0.7.0"):
                packed_user_op.to_eip712_struct(aa_version, chain_id)

            # nothing else to test
            return

        eip712_struct = packed_user_op.to_eip712_struct(aa_version, chain_id)

        # Verify structure
        assert "types" in eip712_struct
        assert "domain" in eip712_struct
        assert "primaryType" in eip712_struct
        assert "message" in eip712_struct

        # Verify types
        types = eip712_struct["types"]
        assert "EIP712Domain" in types
        assert "PackedUserOperation" in types

        # Verify domain
        domain = eip712_struct["domain"]
        assert domain["name"] == (
            "ERC4337" if aa_version != AAVersion.MDT else "MultiSigDeleGator"
        )
        assert domain["version"] == "1"
        assert domain["chainId"] == chain_id
        assert domain["verifyingContract"] == (
            ENTRYPOINT_V08 if aa_version != AAVersion.MDT else packed_user_op.sender
        )

        # Verify primary type
        assert eip712_struct["primaryType"] == "PackedUserOperation"

        # Verify message contains all required fields
        message = eip712_struct["message"]
        expected_fields = {
            "sender",
            "nonce",
            "initCode",
            "callData",
            "accountGasLimits",
            "preVerificationGas",
            "gasFees",
            "paymasterAndData",
        }
        if aa_version == AAVersion.MDT:
            expected_fields.add("entryPoint")

        assert set(message.keys()) == expected_fields

    def test_to_v07_hash(self, sample_user_op):
        """Test V0.7 encoding generation"""
        packed_user_op = PackedUserOperation.from_user_operation(sample_user_op)

        chain_id = 1
        nucypher_core_v07_hash = packed_user_op.to_v07_hash(chain_id)

        # Should be bytes
        assert isinstance(nucypher_core_v07_hash, bytes)

        # try recreating encoding and see if it matches
        encoded_packed_user_op = encode(
            [
                "address",
                "uint256",
                "bytes32",
                "bytes32",
                "bytes32",
                "uint256",
                "bytes32",
                "bytes32",
            ],
            [
                packed_user_op.sender,
                packed_user_op.nonce,
                keccak(packed_user_op.init_code),
                keccak(packed_user_op.call_data),
                packed_user_op.account_gas_limits,
                packed_user_op.pre_verification_gas,
                packed_user_op.gas_fees,
                keccak(packed_user_op.paymaster_and_data),
            ],
        )
        expected_v07_hash = keccak(
            encode(
                ["bytes32", "address", "uint256"],
                [keccak(encoded_packed_user_op), ENTRYPOINT_V07, chain_id],
            )
        )
        assert expected_v07_hash == nucypher_core_v07_hash

    @pytest.mark.parametrize(
        "aa_version", [AAVersion.V07, AAVersion.V08, AAVersion.MDT]
    )
    def test_sign_method(self, aa_version, mocker, sample_user_op):
        """Test signing functionality with transacting power"""
        # Create a test private key and account
        private_key = "0x" + "1" * 64
        account = Account.from_key(private_key)
        aa_version = AAVersion.V08
        chain_id = 1

        # Create a mock transacting power that behaves like the real one
        mock_transacting_power = Mock()

        def mock_sign_message_eip712(message, standardize):
            # Sign the message using the test private key
            # message is now the EIP-712 struct dictionary
            signable_message = encode_typed_data(full_message=message)
            signed_message = account.sign_message(signable_message)
            return signed_message.messageHash, signed_message.signature

        def mock_sign_message_eip191(message, standardize):
            # Sign the message using the test private key
            signable_message = encode_defunct(primitive=message)
            signed_message = account.sign_message(
                signable_message=signable_message,
            )
            return signed_message.messageHash, signed_message.signature

        sign_eip712_spy = mocker.spy(mock_transacting_power, "sign_message_eip712")
        sign_eip191_spy = mocker.spy(mock_transacting_power, "sign_message_eip191")

        sign_eip712_spy.side_effect = mock_sign_message_eip712
        sign_eip191_spy.side_effect = mock_sign_message_eip191

        # Sign the packed user operation
        packed_user_op = PackedUserOperation.from_user_operation(sample_user_op)
        message_hash, signature = sign_packed_user_operation(
            packed_user_op, mock_transacting_power, aa_version, chain_id
        )

        # Verify the signature is valid by reconstructing the message
        if aa_version != AAVersion.V07:
            eip712_struct = packed_user_op.to_eip712_struct(aa_version, chain_id)
            msg = encode_typed_data(full_message=eip712_struct)
            assert sign_eip712_spy.call_count == 1, "eip712 signing performed"
            assert sign_eip191_spy.call_count == 0, "eip191 signing not performed"
        else:
            v07_hash = packed_user_op.to_v07_hash(chain_id)
            msg = encode_defunct(primitive=v07_hash)
            assert sign_eip191_spy.call_count == 1, "eip191 signing performed"
            assert sign_eip712_spy.call_count == 0, "eip712 signing not performed"

        recovered_address = Account.recover_message(msg, signature=signature)
        expected_address = account.address
        assert recovered_address == expected_address

        # Verify the returned message hash matches
        assert message_hash == _hash_eip191_message(msg)

    def test_gas_limits_edge_cases(self):
        """Test edge cases for gas limits"""
        # Test maximum values
        max_uint128 = (2**128) - 1
        user_op = UserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=0,
            call_data=b"",
            call_gas_limit=max_uint128,
            verification_gas_limit=max_uint128,
            pre_verification_gas=0,
            max_fee_per_gas=0,
            max_priority_fee_per_gas=0,
        )

        packed_user_op = PackedUserOperation.from_user_operation(user_op)
        assert len(packed_user_op.account_gas_limits) == 32

        # Test zero values
        user_op_zero = UserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=0,
            call_data=b"",
            call_gas_limit=0,
            verification_gas_limit=0,
            pre_verification_gas=0,
            max_fee_per_gas=0,
            max_priority_fee_per_gas=0,
        )

        packed_user_op = PackedUserOperation.from_user_operation(user_op_zero)
        assert packed_user_op.account_gas_limits == b"\x00" * 32

    def test_fee_edge_cases(self):
        """Test edge cases for fee values"""
        # Test maximum values
        max_uint128 = (2**128) - 1
        user_op = UserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=0,
            call_data=b"",
            call_gas_limit=0,
            verification_gas_limit=0,
            pre_verification_gas=0,
            max_priority_fee_per_gas=max_uint128,
            max_fee_per_gas=max_uint128,
        )

        packed_user_op = PackedUserOperation.from_user_operation(user_op)
        assert len(packed_user_op.gas_fees) == 32

        # Test zeros
        user_op = UserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=0,
            call_data=b"",
            call_gas_limit=0,
            verification_gas_limit=0,
            pre_verification_gas=0,
            max_priority_fee_per_gas=0,
            max_fee_per_gas=0,
        )
        packed_user_op = PackedUserOperation.from_user_operation(user_op)
        assert packed_user_op.gas_fees == b"\x00" * 32


class TestEncodeFunctionCall:
    """Test suite for encode_function_call function"""

    def test_simple_function_encoding(self):
        """Test encoding a simple function call"""
        signature = "transfer(address,uint256)"
        args = ["0x1234567890123456789012345678901234567890", 1000]

        encoded = encode_function_call(signature, args)

        # Should start with function selector (4 bytes)
        assert len(encoded) >= 4

        # Verify selector
        expected_selector = keccak(text=signature)[:4]
        assert encoded[:4] == expected_selector

    def test_function_with_no_args(self):
        """Test encoding function with no arguments"""
        signature = "totalSupply()"
        args = []

        encoded = encode_function_call(signature, args)

        # Should be exactly 4 bytes (just the selector)
        assert len(encoded) == 4

        expected_selector = keccak(text=signature)[:4]
        assert encoded == expected_selector

    def test_function_with_bytes_arg(self):
        """Test encoding function with bytes argument"""
        signature = "execute(address,uint256,bytes)"
        args = ["0x1234567890123456789012345678901234567890", 0, b"\x12\x34\x56\x78"]

        encoded = encode_function_call(signature, args)

        # Should contain selector + encoded args
        assert len(encoded) > 4

        expected_selector = keccak(text=signature)[:4]
        assert encoded[:4] == expected_selector

    def test_function_with_array_args(self):
        """Test encoding function with array arguments"""
        signature = "safeBatchTransferFrom(address,address,uint256[],uint256[],bytes)"
        args = [
            "0x1234567890123456789012345678901234567890",
            "0x9876543210987654321098765432109876543210",
            [1, 2, 3],
            [100, 200, 300],
            b"",
        ]

        encoded = encode_function_call(signature, args)

        assert len(encoded) > 4
        expected_selector = keccak(text=signature)[:4]
        assert encoded[:4] == expected_selector


class TestHelperFunctions:
    """Test suite for helper functions that create specific UserOperations"""

    @pytest.fixture
    def common_params(self):
        """Common parameters for UserOperation creation"""
        return {
            "sender": "0x1234567890123456789012345678901234567890",
            "nonce": 1,
            "verification_gas_limit": 100000,
            "call_gas_limit": 200000,
            "pre_verification_gas": 21000,
            "max_priority_fee_per_gas": 1000000000,
            "max_fee_per_gas": 2000000000,
        }

    def test_create_eth_transfer(self, common_params):
        """Test creating ETH transfer UserOperation"""
        to = "0x9876543210987654321098765432109876543210"
        value = 1000000000000000000  # 1 ETH in wei

        user_op = create_eth_transfer(
            common_params["sender"],
            common_params["nonce"],
            to,
            value,
            **{k: v for k, v in common_params.items() if k not in ["sender", "nonce"]},
        )

        assert isinstance(user_op, UserOperation)
        assert user_op.sender == common_params["sender"]
        assert user_op.nonce == common_params["nonce"]
        assert user_op.factory is None
        assert user_op.factory_data is None
        assert len(user_op.call_data) > 0

        # Verify the call data contains the execute function call
        expected_selector = keccak(text="execute(address,uint256,bytes)")[:4]
        assert user_op.call_data[:4] == expected_selector

    def test_create_erc20_transfer(self, common_params):
        """Test creating ERC20 transfer UserOperation"""
        token = "0xA0b86a33E6441b8435b662f0E2d0B8A0E6E6E6E6"
        to = "0x9876543210987654321098765432109876543210"
        amount = 1000000  # 1 USDC (6 decimals)

        user_op = create_erc20_transfer(
            common_params["sender"],
            common_params["nonce"],
            token,
            to,
            amount,
            **{k: v for k, v in common_params.items() if k not in ["sender", "nonce"]},
        )

        assert isinstance(user_op, UserOperation)
        assert user_op.sender == common_params["sender"]
        assert user_op.nonce == common_params["nonce"]
        assert len(user_op.call_data) > 0

        # Verify the call data contains the execute function call
        expected_selector = keccak(text="execute(address,uint256,bytes)")[:4]
        assert user_op.call_data[:4] == expected_selector

    def test_create_erc20_approve(self, common_params):
        """Test creating ERC20 approve UserOperation"""
        token = "0xA0b86a33E6441b8435b662f0E2d0B8A0E6E6E6E6"
        spender = "0x9876543210987654321098765432109876543210"
        amount = 1000000

        user_op = create_erc20_approve(
            common_params["sender"],
            common_params["nonce"],
            token,
            spender,
            amount,
            **{k: v for k, v in common_params.items() if k not in ["sender", "nonce"]},
        )

        assert isinstance(user_op, UserOperation)
        assert user_op.sender == common_params["sender"]
        assert user_op.nonce == common_params["nonce"]
        assert len(user_op.call_data) > 0

    def test_create_contract_call(self, common_params):
        """Test creating generic contract call UserOperation"""
        target = "0xA0b86a33E6441b8435b662f0E2d0B8A0E6E6E6E6"
        data = b"\x12\x34\x56\x78"
        value = 0

        user_op = create_contract_call(
            common_params["sender"],
            common_params["nonce"],
            target,
            data,
            value,
            **{k: v for k, v in common_params.items() if k not in ["sender", "nonce"]},
        )

        assert isinstance(user_op, UserOperation)
        assert user_op.sender == common_params["sender"]
        assert user_op.nonce == common_params["nonce"]
        assert len(user_op.call_data) > 0

    def test_create_contract_call_with_value(self, common_params):
        """Test creating contract call with ETH value"""
        target = "0xA0b86a33E6441b8435b662f0E2d0B8A0E6E6E6E6"
        data = b"\x12\x34\x56\x78"
        value = 1000000000000000000  # 1 ETH

        user_op = create_contract_call(
            common_params["sender"],
            common_params["nonce"],
            target,
            data,
            value,
            **{k: v for k, v in common_params.items() if k not in ["sender", "nonce"]},
        )

        assert isinstance(user_op, UserOperation)
        assert user_op.sender == common_params["sender"]
        assert user_op.nonce == common_params["nonce"]
        assert len(user_op.call_data) > 0


class TestERC4337Compatibility:
    """Test suite for ERC-4337 specification compatibility"""

    def test_user_operation_fields_match_spec(self):
        """Test that UserOperation fields match ERC-4337 specification"""
        user_op = UserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=1,
            call_data=b"",
            **COMMON_REQUIRED_USER_OP_GAS_VALUES,
        )

        # Verify all required fields exist according to ERC-4337
        required_fields = [
            "sender",
            "nonce",
            "factory",
            "factory_data",
            "call_data",
            "verification_gas_limit",
            "call_gas_limit",
            "pre_verification_gas",
            "max_priority_fee_per_gas",
            "max_fee_per_gas",
            "paymaster",
            "paymaster_verification_gas_limit",
            "paymaster_post_op_gas_limit",
            "paymaster_data",
        ]

        for field in required_fields:
            assert hasattr(user_op, field), f"Missing required field: {field}"

    def test_packed_user_op_matches_spec(self, sample_user_op):
        """Test that PackedUserOperation matches ERC-4337 packed format"""
        packed_user_op = PackedUserOperation.from_user_operation(sample_user_op)

        # According to ERC-4337, packed format should have these exact keys
        expected_keys = {
            "sender",
            "nonce",
            "initCode",
            "callData",
            "accountGasLimits",
            "preVerificationGas",
            "gasFees",
            "paymasterAndData",
        }

        for field in expected_keys:
            assert hasattr(
                packed_user_op, camel_case_to_snake(field)
            ), f"Missing required field: {field}"

        # Verify data types
        assert isinstance(packed_user_op.sender, str)
        assert isinstance(packed_user_op.nonce, int)
        assert isinstance(packed_user_op.init_code, bytes)
        assert isinstance(packed_user_op.call_data, bytes)
        assert isinstance(packed_user_op.account_gas_limits, bytes)
        assert isinstance(packed_user_op.pre_verification_gas, int)
        assert isinstance(packed_user_op.gas_fees, bytes)
        assert isinstance(packed_user_op.paymaster_and_data, bytes)

        # Verify packed field lengths
        assert len(packed_user_op.account_gas_limits) == 32
        assert len(packed_user_op.gas_fees) == 32

    def test_eip712_domain_matches_spec(self, sample_user_op):
        """Test that EIP-712 domain matches ERC-4337 specification"""
        chain_id = 1

        packed_user_op = PackedUserOperation.from_user_operation(sample_user_op)
        eip712_struct = packed_user_op.to_eip712_struct(AAVersion.V08, chain_id)

        # Verify EIP-712 domain according to ERC-4337
        domain = eip712_struct["domain"]
        assert domain["name"] == "ERC4337"
        assert domain["version"] == "1"
        assert domain["chainId"] == chain_id
        assert domain["verifyingContract"] == ENTRYPOINT_V08

        # Verify types structure
        types = eip712_struct["types"]
        assert "EIP712Domain" in types
        assert "PackedUserOperation" in types

        # Verify UserOperation type fields match specification
        user_op_type = types["PackedUserOperation"]
        expected_fields = [
            "sender",
            "nonce",
            "initCode",
            "callData",
            "accountGasLimits",
            "preVerificationGas",
            "gasFees",
            "paymasterAndData",
        ]

        actual_fields = [field["name"] for field in user_op_type]
        assert actual_fields == expected_fields

    def test_address_checksum_validation(self):
        """Test that addresses are properly checksummed"""
        # Test with non-checksummed address
        user_op = UserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=1,
            call_data=b"",
            **COMMON_REQUIRED_USER_OP_GAS_VALUES,
        )

        # All helper functions should handle address checksumming
        to_addr = "0x9876543210987654321098765432109876543210"

        # Test ERC20 transfer
        erc20_op = create_erc20_transfer(user_op.sender, 1, to_addr, to_addr, 1000)
        assert isinstance(erc20_op, UserOperation)

        # Test ETH transfer
        eth_op = create_eth_transfer(user_op.sender, 1, to_addr, 1000)
        assert isinstance(eth_op, UserOperation)

    @pytest.fixture
    def sample_user_op(self):
        """Create a sample PackedUserOperation for testing"""
        return UserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=1,
            factory="0x27BbA3872e3e00632A200C08F7CD9E999a36BA85",
            factory_data=b"\x12\x34",
            call_data=b"\x56\x78",
            verification_gas_limit=100000,
            call_gas_limit=200000,
            pre_verification_gas=21000,
            max_priority_fee_per_gas=1000000000,
            max_fee_per_gas=2000000000,
            paymaster="0x9876543210987654321098765432109876543210",
            paymaster_verification_gas_limit=50000,
            paymaster_post_op_gas_limit=30000,
            paymaster_data=b"\xab\xcd",
        )


class TestErrorHandling:
    """Test suite for error handling and edge cases"""

    def test_empty_signature_signing(self):
        """Test signing with empty initial signature using transacting power"""

        user_op = UserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=1,
            call_data=b"",
            **COMMON_REQUIRED_USER_OP_GAS_VALUES,
        )

        # Create a test private key and account
        private_key = "0x" + "1" * 64
        account = Account.from_key(private_key)
        chain_id = 1

        # Create a mock transacting power that behaves like the real one
        mock_transacting_power = Mock()

        def mock_sign_message_eip712(message, standardize):
            # Sign the message using the test private key
            # message is now the EIP-712 struct dictionary
            signable_message = encode_typed_data(full_message=message)
            signed_message = account.sign_message(signable_message)
            return signed_message.messageHash, signed_message.signature

        mock_transacting_power.sign_message_eip712 = mock_sign_message_eip712

        # Should work even with empty initial signature
        packed_user_op = PackedUserOperation.from_user_operation(user_op)
        message_hash, signature = sign_packed_user_operation(
            packed_user_op, mock_transacting_power, AAVersion.V08, chain_id
        )
        assert len(signature) == 65
        assert message_hash == _hash_eip191_message(
            encode_typed_data(
                full_message=packed_user_op.to_eip712_struct(AAVersion.V08, chain_id)
            )
        )
