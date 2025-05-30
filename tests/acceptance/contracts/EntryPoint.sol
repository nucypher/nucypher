// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin530/contracts/interfaces/draft-IERC4337.sol";
import "@openzeppelin530/contracts/utils/cryptography/EIP712.sol";

contract EntryPoint is EIP712 {
    string constant internal DOMAIN_NAME = "ERC4337";
    string constant internal DOMAIN_VERSION = "1";

    bytes32 internal constant PACKED_USEROP_TYPEHASH = keccak256(
        "PackedUserOperation(address sender,uint256 nonce,bytes initCode,bytes callData,bytes32 accountGasLimits,uint256 preVerificationGas,bytes32 gasFees,bytes paymasterAndData)"
    );

    constructor() EIP712(DOMAIN_NAME, DOMAIN_VERSION) {
    }

    function encode(
        PackedUserOperation calldata userOp
    ) internal pure returns (bytes memory ret) {
        address sender = userOp.sender;
        uint256 nonce = userOp.nonce;
        bytes32 hashInitCode = keccak256(userOp.initCode);
        bytes32 hashCallData = keccak256(userOp.callData);
        bytes32 accountGasLimits = userOp.accountGasLimits;
        uint256 preVerificationGas = userOp.preVerificationGas;
        bytes32 gasFees = userOp.gasFees;
        bytes32 hashPaymasterAndData = keccak256(userOp.paymasterAndData);

        return abi.encode(
            PACKED_USEROP_TYPEHASH,
            sender, nonce,
            hashInitCode, hashCallData,
            accountGasLimits, preVerificationGas, gasFees,
            hashPaymasterAndData
        );
    }

    function hashStruct(
        PackedUserOperation calldata userOp
    ) internal view returns (bytes32) {
        bytes memory encodedOp = encode(userOp);
        return keccak256(encodedOp);
    }

    function getUserOpHashV8(
        PackedUserOperation calldata userOp
    ) public view returns (bytes32) {
        bytes memory encodedOp = encode(userOp);
        return _hashTypedDataV4(hashStruct(userOp));
    }
}
