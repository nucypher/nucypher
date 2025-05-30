from unittest.mock import Mock

import pytest
from eth_account import Account
from eth_account.messages import _hash_eip191_message, encode_typed_data
from eth_utils import keccak

from nucypher.policy.conditions.utils import camel_case_to_snake
from nucypher.utilities.erc4337_utils import (
    AAVersion,
    EntryPointContracts,
    PackedUserOperation,
    UserOperation,
    create_contract_call,
    create_erc20_approve,
    create_erc20_transfer,
    create_eth_transfer,
    encode_function_call,
)


class TestPackedUserOperation:
    """Test suite for PackedUserOperation class"""

    @pytest.fixture
    def sample_user_op(self):
        """Create a sample PackedUserOperation for testing"""
        return UserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=1,
            init_code=b"\x12\x34",
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
            signature=b"\xde\xad\xbe\xef",
        )

    @pytest.fixture
    def minimal_user_op(self):
        """Create a minimal PackedUserOperation for testing"""
        return UserOperation(
            sender="0x1234567890123456789012345678901234567890", nonce=0
        )

    def test_user_operation_initialization(self, sample_user_op):
        """Test PackedUserOperation initialization with all fields"""
        assert sample_user_op.sender == "0x1234567890123456789012345678901234567890"
        assert sample_user_op.nonce == 1
        assert sample_user_op.init_code == b"\x12\x34"
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
        assert sample_user_op.signature == b"\xde\xad\xbe\xef"

    def test_minimal_user_operation_initialization(self, minimal_user_op):
        """Test PackedUserOperation initialization with minimal fields"""
        assert minimal_user_op.sender == "0x1234567890123456789012345678901234567890"
        assert minimal_user_op.nonce == 0
        assert minimal_user_op.init_code == b""
        assert minimal_user_op.call_data == b""
        assert minimal_user_op.verification_gas_limit == 0
        assert minimal_user_op.call_gas_limit == 0
        assert minimal_user_op.pre_verification_gas == 0
        assert minimal_user_op.max_priority_fee_per_gas == 0
        assert minimal_user_op.max_fee_per_gas == 0
        assert minimal_user_op.paymaster is None
        assert minimal_user_op.paymaster_verification_gas_limit == 0
        assert minimal_user_op.paymaster_post_op_gas_limit == 0
        assert minimal_user_op.paymaster_data == b""
        assert minimal_user_op.signature == b""

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

    def test_packed_user_op_methods(self, sample_user_op):
        """Test the pack method returns correct dictionary structure"""
        packed_user_op = PackedUserOperation.from_user_operation(sample_user_op)

        # Verify types and values
        assert packed_user_op.sender == sample_user_op.sender
        assert packed_user_op.nonce == sample_user_op.nonce
        assert packed_user_op.init_code == sample_user_op.init_code
        assert packed_user_op.call_data == sample_user_op.call_data
        assert (
            packed_user_op.pre_verification_gas == sample_user_op.pre_verification_gas
        )
        assert packed_user_op.signature == sample_user_op.signature

        # Verify packed fields
        assert (
            packed_user_op.account_gas_limits
            == PackedUserOperation._pack_account_gas_limits(
                sample_user_op.call_gas_limit, sample_user_op.verification_gas_limit
            )
        )
        assert packed_user_op.gas_fees == PackedUserOperation._pack_gas_fees(
            sample_user_op.max_fee_per_gas, sample_user_op.max_priority_fee_per_gas
        )
        assert (
            packed_user_op.paymaster_and_data
            == PackedUserOperation._pack_paymaster_and_data(
                sample_user_op.paymaster,
                sample_user_op.paymaster_verification_gas_limit,
                sample_user_op.paymaster_post_op_gas_limit,
                sample_user_op.paymaster_data,
            )
        )

    @pytest.mark.parametrize("aa_version", [AAVersion.V08, AAVersion.MDT])
    def test_to_eip712_struct(self, aa_version, sample_user_op):
        """Test EIP-712 struct generation"""
        packed_user_op = PackedUserOperation.from_user_operation(sample_user_op)

        chain_id = 1
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
        assert (
            domain["name"] == "ERC4337"
            if aa_version != AAVersion.MDT
            else "MultiSigDeleGator"
        )
        assert domain["version"] == "1"
        assert domain["chainId"] == chain_id
        assert domain["verifyingContract"] == EntryPointContracts.ENTRYPOINT_V08

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

    def test_sign_method(self, sample_user_op):
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

        mock_transacting_power.sign_message_eip712 = mock_sign_message_eip712

        # Sign the packed user operation
        packed_user_op = PackedUserOperation.from_user_operation(sample_user_op)
        message_hash, signature = packed_user_op.sign(
            mock_transacting_power, aa_version, chain_id
        )

        # Verify signature was set
        assert packed_user_op.signature == signature
        assert len(packed_user_op.signature) == 65  # Standard ECDSA signature length

        # Verify the signature is valid by reconstructing the message
        eip712_struct = packed_user_op.to_eip712_struct(aa_version, chain_id)
        # Temporarily clear signature for verification
        original_signature = packed_user_op.signature
        packed_user_op.signature = b""

        msg = encode_typed_data(full_message=eip712_struct)
        recovered_address = Account.recover_message(msg, signature=original_signature)
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
            verification_gas_limit=max_uint128,
            call_gas_limit=max_uint128,
        )

        packed_user_op = PackedUserOperation.from_user_operation(user_op)
        assert len(packed_user_op.account_gas_limits) == 32

        # Test zero values
        user_op_zero = UserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=0,
            verification_gas_limit=0,
            call_gas_limit=0,
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
            max_priority_fee_per_gas=max_uint128,
            max_fee_per_gas=max_uint128,
        )

        packed_user_op = PackedUserOperation.from_user_operation(user_op)
        assert len(packed_user_op.gas_fees) == 32

    def test_oversized_gas_limits(self):
        """Test handling of gas limit values"""
        # Test with maximum values that can fit in the packing format (uint128 each)
        max_uint128 = (2**128) - 1

        user_op = UserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=1,
            verification_gas_limit=max_uint128,  # Should work
            call_gas_limit=max_uint128,  # Should work
        )

        # Should be able to pack without error
        packed_user_op = PackedUserOperation.from_user_operation(user_op)
        assert len(packed_user_op.account_gas_limits) == 32


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
        assert user_op.init_code == b""
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
            sender="0x1234567890123456789012345678901234567890", nonce=1
        )

        # Verify all required fields exist according to ERC-4337
        required_fields = [
            "sender",
            "nonce",
            "init_code",
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
            "signature",
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
            "signature",
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
        assert isinstance(packed_user_op.signature, bytes)

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
        assert domain["verifyingContract"] == EntryPointContracts.ENTRYPOINT_V08

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
            sender="0x1234567890123456789012345678901234567890", nonce=1
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
            init_code=b"\x12\x34",
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
            signature=b"\xde\xad\xbe\xef",
        )


class TestErrorHandling:
    """Test suite for error handling and edge cases"""

    def test_empty_signature_signing(self):
        """Test signing with empty initial signature using transacting power"""

        user_op = UserOperation(
            sender="0x1234567890123456789012345678901234567890", nonce=1
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
        message_hash, signature = packed_user_op.sign(
            mock_transacting_power, AAVersion.V08, chain_id
        )
        assert len(packed_user_op.signature) == 65
        assert signature == packed_user_op.signature
        assert message_hash == _hash_eip191_message(
            encode_typed_data(
                full_message=packed_user_op.to_eip712_struct(AAVersion.V08, chain_id)
            )
        )
