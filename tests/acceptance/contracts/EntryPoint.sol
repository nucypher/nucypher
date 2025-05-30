// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin530/contracts/account/utils/draft-ERC4337Utils.sol";
import "@openzeppelin530/contracts/interfaces/draft-IERC4337.sol";
import "@openzeppelin530/contracts/utils/cryptography/EIP712.sol";
import "@openzeppelin530/contracts/utils/cryptography/MessageHashUtils.sol";

contract EntryPoint is EIP712 {
    string constant internal DOMAIN_NAME = "ERC4337";
    string constant internal DOMAIN_VERSION = "1";

    bytes32 private constant TYPE_HASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");

    bytes32 internal constant PACKED_USEROP_TYPEHASH = keccak256(
        "PackedUserOperation(address sender,uint256 nonce,bytes initCode,bytes callData,bytes32 accountGasLimits,uint256 preVerificationGas,bytes32 gasFees,bytes paymasterAndData)"
    );

    bytes32 public constant PACKED_USEROP_TYPEHASH_MDT = keccak256(
        "PackedUserOperation(address sender,uint256 nonce,bytes initCode,bytes callData,bytes32 accountGasLimits,uint256 preVerificationGas,bytes32 gasFees,bytes paymasterAndData,address entryPoint)"
    );

    constructor() EIP712(DOMAIN_NAME, DOMAIN_VERSION) {
    }

    function hashV8(
        PackedUserOperation calldata userOp
    ) internal pure returns (bytes32) {
        address sender = userOp.sender;
        uint256 nonce = userOp.nonce;
        bytes32 hashInitCode = keccak256(userOp.initCode);
        bytes32 hashCallData = keccak256(userOp.callData);
        bytes32 accountGasLimits = userOp.accountGasLimits;
        uint256 preVerificationGas = userOp.preVerificationGas;
        bytes32 gasFees = userOp.gasFees;
        bytes32 hashPaymasterAndData = keccak256(userOp.paymasterAndData);

        return keccak256(abi.encode(
            PACKED_USEROP_TYPEHASH,
            sender, nonce,
            hashInitCode, hashCallData,
            accountGasLimits, preVerificationGas, gasFees,
            hashPaymasterAndData
        ));
    }

    /// @dev Mimics hashing functionality of EntryPoint v0.8.0
    function getUserOpHashV8(
        PackedUserOperation calldata userOp
    ) public view returns (bytes32) {
        return _hashTypedDataV4(hashV8(userOp));
    }

    function hashMDT(
        PackedUserOperation calldata userOp
    ) internal view returns (bytes32) {
        return keccak256(
            abi.encode(
                PACKED_USEROP_TYPEHASH_MDT,
                userOp.sender,
                userOp.nonce,
                keccak256(userOp.initCode),
                keccak256(userOp.callData),
                userOp.accountGasLimits,
                userOp.preVerificationGas,
                userOp.gasFees,
                keccak256(userOp.paymasterAndData),
                address(this)
            )
        );
    }

    function getDomainSeparatorMDT() public view returns (bytes32) {
        bytes32 _hashedName = keccak256(bytes("MultiSigDeleGator"));
        bytes32 _hashedVersion = keccak256(bytes("1"));
        return keccak256(abi.encode(TYPE_HASH, _hashedName, _hashedVersion, block.chainid, address(this)));
    }

    /// @dev Mimics hashing functionality of MDT 1.3.0
    function getUserOpHashMDT(
        PackedUserOperation calldata userOp
    ) public view returns (bytes32) {
         return MessageHashUtils.toTypedDataHash(getDomainSeparatorMDT(), hashMDT(userOp));
    }

    //
    // Used for testing of PackedUserOperation packed values
    //

    /// @dev Returns `verificationGasLimit` from the {PackedUserOperation}.
    function verificationGasLimit(PackedUserOperation calldata userOp) public pure returns (uint256) {
        return ERC4337Utils.verificationGasLimit(userOp);
    }

    /// @dev Returns `callGasLimit` from the {PackedUserOperation}.
    function callGasLimit(PackedUserOperation calldata userOp) public pure returns (uint256) {
        return ERC4337Utils.callGasLimit(userOp);
    }

    /// @dev Returns the first section of `gasFees` from the {PackedUserOperation}.
    function maxPriorityFeePerGas(PackedUserOperation calldata userOp) public pure returns (uint256) {
        return ERC4337Utils.maxPriorityFeePerGas(userOp);
    }

    /// @dev Returns the second section of `gasFees` from the {PackedUserOperation}.
    function maxFeePerGas(PackedUserOperation calldata userOp) public pure returns (uint256) {
        return ERC4337Utils.maxFeePerGas(userOp);
    }

    /// @dev Returns the first section of `paymasterAndData` from the {PackedUserOperation}.
    function paymaster(PackedUserOperation calldata userOp) public pure returns (address) {
        return ERC4337Utils.paymaster(userOp);
    }

    /// @dev Returns the second section of `paymasterAndData` from the {PackedUserOperation}.
    function paymasterVerificationGasLimit(PackedUserOperation calldata userOp) public pure returns (uint256) {
        return ERC4337Utils.paymasterVerificationGasLimit(userOp);
    }

    /// @dev Returns the third section of `paymasterAndData` from the {PackedUserOperation}.
    function paymasterPostOpGasLimit(PackedUserOperation calldata userOp) public pure returns (uint256) {
        return ERC4337Utils.paymasterPostOpGasLimit(userOp);
    }

    /// @dev Returns the fourth section of `paymasterAndData` from the {PackedUserOperation}.
    function paymasterData(PackedUserOperation calldata userOp) public pure returns (bytes calldata) {
        return ERC4337Utils.paymasterData(userOp);
    }
}
