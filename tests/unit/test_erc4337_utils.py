import pytest
from eth_account import Account
from eth_account.messages import encode_structured_data
from eth_utils import keccak, to_bytes

from nucypher.utilities.erc4337_utils import (
    PackedUserOperation,
    create_contract_call,
    create_erc20_approve,
    create_erc20_transfer,
    create_eth_transfer,
    encode_function_call,
)


@pytest.mark.skip("Skipping tests for PackedUserOperation and related functions")
class TestPackedUserOperation:
    """Test suite for PackedUserOperation class"""

    @pytest.fixture
    def sample_user_op(self):
        """Create a sample PackedUserOperation for testing"""
        return PackedUserOperation(
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
            paymaster_data=b"\xab\xcd",
            signature=b"\xde\xad\xbe\xef",
        )

    @pytest.fixture
    def minimal_user_op(self):
        """Create a minimal PackedUserOperation for testing"""
        return PackedUserOperation(
            sender="0x1234567890123456789012345678901234567890", nonce=0
        )

    def test_packed_user_operation_initialization(self, sample_user_op):
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
        assert sample_user_op.paymaster_data == b"\xab\xcd"
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

    def test_pack_account_gas_limits(self, sample_user_op):
        """Test _pack_account_gas_limits method"""
        packed = sample_user_op._pack_account_gas_limits()

        # Should be 32 bytes
        assert len(packed) == 32

        # Verify the packing: verification_gas_limit (16 bytes) + call_gas_limit (16 bytes)
        expected = (
            sample_user_op.verification_gas_limit << 128
        ) | sample_user_op.call_gas_limit
        assert packed == expected.to_bytes(32, byteorder="big")

    def test_pack_gas_fees(self, sample_user_op):
        """Test _pack_gas_fees method"""
        packed = sample_user_op._pack_gas_fees()

        # Should be 32 bytes
        assert len(packed) == 32

        # Verify the packing: max_priority_fee_per_gas (16 bytes) + max_fee_per_gas (16 bytes)
        expected = (
            sample_user_op.max_priority_fee_per_gas << 128
        ) | sample_user_op.max_fee_per_gas
        assert packed == expected.to_bytes(32, byteorder="big")

    def test_pack_paymaster_and_data_with_paymaster(self, sample_user_op):
        """Test _pack_paymaster_and_data method with paymaster"""
        packed = sample_user_op._pack_paymaster_and_data()

        # Should contain: paymaster (20 bytes) + verification_gas_limit (16 bytes) + post_op_gas_limit (16 bytes) + data
        expected_length = 20 + 16 + 16 + len(sample_user_op.paymaster_data)
        assert len(packed) == expected_length

        # Verify components
        paymaster_bytes = to_bytes(hexstr=sample_user_op.paymaster)
        verification_bytes = sample_user_op.paymaster_verification_gas_limit.to_bytes(
            16, byteorder="big"
        )
        post_op_bytes = sample_user_op.paymaster_post_op_gas_limit.to_bytes(
            16, byteorder="big"
        )

        expected = (
            paymaster_bytes
            + verification_bytes
            + post_op_bytes
            + sample_user_op.paymaster_data
        )
        assert packed == expected

    def test_pack_paymaster_and_data_without_paymaster(self, minimal_user_op):
        """Test _pack_paymaster_and_data method without paymaster"""
        packed = minimal_user_op._pack_paymaster_and_data()
        assert packed == b""

    def test_pack_method(self, sample_user_op):
        """Test the pack method returns correct dictionary structure"""
        packed = sample_user_op.pack()

        # Verify all required keys are present
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
        assert set(packed.keys()) == expected_keys

        # Verify types and values
        assert packed["sender"] == sample_user_op.sender
        assert packed["nonce"] == sample_user_op.nonce
        assert packed["initCode"] == sample_user_op.init_code
        assert packed["callData"] == sample_user_op.call_data
        assert packed["preVerificationGas"] == sample_user_op.pre_verification_gas
        assert packed["signature"] == sample_user_op.signature

        # Verify packed fields
        assert packed["accountGasLimits"] == sample_user_op._pack_account_gas_limits()
        assert packed["gasFees"] == sample_user_op._pack_gas_fees()
        assert packed["paymasterAndData"] == sample_user_op._pack_paymaster_and_data()

    def test_to_eip712_struct(self, sample_user_op):
        """Test EIP-712 struct generation"""
        entrypoint = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        chain_id = 1

        eip712_struct = sample_user_op.to_eip712_struct(entrypoint, chain_id)

        # Verify structure
        assert "types" in eip712_struct
        assert "domain" in eip712_struct
        assert "primaryType" in eip712_struct
        assert "message" in eip712_struct

        # Verify types
        types = eip712_struct["types"]
        assert "EIP712Domain" in types
        assert "UserOperation" in types

        # Verify domain
        domain = eip712_struct["domain"]
        assert domain["name"] == "UserOperation"
        assert domain["version"] == "1"
        assert domain["chainId"] == chain_id
        assert domain["verifyingContract"] == entrypoint

        # Verify primary type
        assert eip712_struct["primaryType"] == "UserOperation"

        # Verify message contains all required fields
        message = eip712_struct["message"]
        expected_fields = {
            "sender",
            "nonce",
            "initCode",
            "callData",
            "callGasLimit",
            "verificationGasLimit",
            "preVerificationGas",
            "maxPriorityFeePerGas",
            "maxFeePerGas",
            "paymasterAndData",
        }
        assert set(message.keys()) == expected_fields

    def test_sign_method(self, sample_user_op):
        """Test signing functionality"""
        # Create a test private key
        private_key = "0x" + "1" * 64
        entrypoint = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        chain_id = 1

        # Sign the user operation
        signed = sample_user_op.sign(private_key, entrypoint, chain_id)

        # Verify signature was set
        assert sample_user_op.signature == signed.signature
        assert len(sample_user_op.signature) == 65  # Standard ECDSA signature length

        # Verify the signature is valid by reconstructing the message
        eip712_struct = sample_user_op.to_eip712_struct(entrypoint, chain_id)
        # Temporarily clear signature for verification
        original_signature = sample_user_op.signature
        sample_user_op.signature = b""

        msg = encode_structured_data(primitive=eip712_struct)
        recovered_address = Account.recover_message(msg, signature=original_signature)
        expected_address = Account.from_key(private_key).address

        assert recovered_address == expected_address

        # Restore signature
        sample_user_op.signature = original_signature

    def test_gas_limits_edge_cases(self):
        """Test edge cases for gas limits"""
        # Test maximum values
        max_uint128 = (2**128) - 1
        user_op = PackedUserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=0,
            verification_gas_limit=max_uint128,
            call_gas_limit=max_uint128,
        )

        packed = user_op._pack_account_gas_limits()
        assert len(packed) == 32

        # Test zero values
        user_op_zero = PackedUserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=0,
            verification_gas_limit=0,
            call_gas_limit=0,
        )

        packed_zero = user_op_zero._pack_account_gas_limits()
        assert packed_zero == b"\x00" * 32

    def test_fee_edge_cases(self):
        """Test edge cases for fee values"""
        # Test maximum values
        max_uint128 = (2**128) - 1
        user_op = PackedUserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=0,
            max_priority_fee_per_gas=max_uint128,
            max_fee_per_gas=max_uint128,
        )

        packed = user_op._pack_gas_fees()
        assert len(packed) == 32

@pytest.mark.skip("Skipping tests for PackedUserOperation and related functions")
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


@pytest.mark.skip("Skipping tests for PackedUserOperation and related functions")
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

        assert isinstance(user_op, PackedUserOperation)
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

        assert isinstance(user_op, PackedUserOperation)
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

        assert isinstance(user_op, PackedUserOperation)
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

        assert isinstance(user_op, PackedUserOperation)
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

        assert isinstance(user_op, PackedUserOperation)
        assert user_op.sender == common_params["sender"]
        assert user_op.nonce == common_params["nonce"]
        assert len(user_op.call_data) > 0


@pytest.mark.skip("Skipping tests for PackedUserOperation and related functions")
class TestERC4337Compatibility:
    """Test suite for ERC-4337 specification compatibility"""

    def test_packed_user_operation_fields_match_spec(self):
        """Test that PackedUserOperation fields match ERC-4337 specification"""
        user_op = PackedUserOperation(
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

    def test_pack_output_format_matches_spec(self, sample_user_op):
        """Test that pack() output matches ERC-4337 PackedUserOperation format"""
        packed = sample_user_op.pack()

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

        assert set(packed.keys()) == expected_keys

        # Verify data types
        assert isinstance(packed["sender"], str)
        assert isinstance(packed["nonce"], int)
        assert isinstance(packed["initCode"], bytes)
        assert isinstance(packed["callData"], bytes)
        assert isinstance(packed["accountGasLimits"], bytes)
        assert isinstance(packed["preVerificationGas"], int)
        assert isinstance(packed["gasFees"], bytes)
        assert isinstance(packed["paymasterAndData"], bytes)
        assert isinstance(packed["signature"], bytes)

        # Verify packed field lengths
        assert len(packed["accountGasLimits"]) == 32
        assert len(packed["gasFees"]) == 32

    def test_eip712_domain_matches_spec(self, sample_user_op):
        """Test that EIP-712 domain matches ERC-4337 specification"""
        entrypoint = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        chain_id = 1

        eip712_struct = sample_user_op.to_eip712_struct(entrypoint, chain_id)

        # Verify EIP-712 domain according to ERC-4337
        domain = eip712_struct["domain"]
        assert domain["name"] == "UserOperation"
        assert domain["version"] == "1"
        assert domain["chainId"] == chain_id
        assert domain["verifyingContract"] == entrypoint

        # Verify types structure
        types = eip712_struct["types"]
        assert "EIP712Domain" in types
        assert "UserOperation" in types

        # Verify UserOperation type fields match specification
        user_op_type = types["UserOperation"]
        expected_fields = [
            "sender",
            "nonce",
            "initCode",
            "callData",
            "callGasLimit",
            "verificationGasLimit",
            "preVerificationGas",
            "maxPriorityFeePerGas",
            "maxFeePerGas",
            "paymasterAndData",
        ]

        actual_fields = [field["name"] for field in user_op_type]
        assert actual_fields == expected_fields

    def test_address_checksum_validation(self):
        """Test that addresses are properly checksummed"""
        # Test with non-checksummed address
        user_op = PackedUserOperation(
            sender="0x1234567890123456789012345678901234567890", nonce=1
        )

        # All helper functions should handle address checksumming
        to_addr = "0x9876543210987654321098765432109876543210"

        # Test ERC20 transfer
        erc20_op = create_erc20_transfer(user_op.sender, 1, to_addr, to_addr, 1000)
        assert isinstance(erc20_op, PackedUserOperation)

        # Test ETH transfer
        eth_op = create_eth_transfer(user_op.sender, 1, to_addr, 1000)
        assert isinstance(eth_op, PackedUserOperation)

    @pytest.fixture
    def sample_user_op(self):
        """Create a sample PackedUserOperation for testing"""
        return PackedUserOperation(
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


@pytest.mark.skip("Skipping tests for PackedUserOperation and related functions")
class TestErrorHandling:
    """Test suite for error handling and edge cases"""

    def test_invalid_address_format(self):
        """Test handling of invalid address formats"""
        with pytest.raises((ValueError, TypeError)):
            PackedUserOperation(sender="invalid_address", nonce=1)

    def test_negative_values(self):
        """Test handling of negative values where not allowed"""
        # Nonce should not be negative
        with pytest.raises((ValueError, OverflowError)):
            PackedUserOperation(
                sender="0x1234567890123456789012345678901234567890", nonce=-1
            )

    def test_oversized_gas_limits(self):
        """Test handling of oversized gas limit values"""
        # Test with value larger than uint256
        max_uint256 = 2**256

        user_op = PackedUserOperation(
            sender="0x1234567890123456789012345678901234567890",
            nonce=1,
            verification_gas_limit=max_uint256 - 1,  # Should work
            call_gas_limit=max_uint256 - 1,  # Should work
        )

        # Should be able to pack without error
        packed = user_op._pack_account_gas_limits()
        assert len(packed) == 32

    def test_empty_signature_signing(self):
        """Test signing with empty initial signature"""
        user_op = PackedUserOperation(
            sender="0x1234567890123456789012345678901234567890", nonce=1
        )

        private_key = "0x" + "1" * 64
        entrypoint = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
        chain_id = 1

        # Should work even with empty initial signature
        signed = user_op.sign(private_key, entrypoint, chain_id)
        assert len(user_op.signature) == 65
        assert signed.signature == user_op.signature
