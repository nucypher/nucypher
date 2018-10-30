pragma solidity ^0.4.25;


/**
* @notice Library to recover address and verify signatures
* @dev Simple wrapper for `ecrecover`
**/
library SignatureVerifier {

    enum HashAlgorithm {KECCAK256, SHA256, RIPEMD160}

    /**
    * @notice Recover signer address from hash and signature
    * @param _hash 32 bytes message hash
    * @param _signature Signature of hash - 32 bytes r + 32 bytes s + 1 byte v (could be 0, 1, 27, 28)
    **/
    function recover(bytes32 _hash, bytes _signature)
        internal
        pure
        returns (address)
    {
        require(_signature.length == 65);

        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := mload(add(_signature, 32))
            s := mload(add(_signature, 64))
            v := byte(0, mload(add(_signature, 96)))
        }

        // Version of signature should be 27 or 28, but 0 and 1 are also possible versions
        if (v < 27) {
            v += 27;
        }
        require(v == 27 || v == 28);
        return ecrecover(_hash, v, r, s);
    }

    /**
    * @notice Transform public key to address
    * @param _publicKey secp256k1 public key
    **/
    function toAddress(bytes _publicKey) internal pure returns (address) {
        return address(keccak256(_publicKey));
    }

    /**
    * @notice Hash using one of pre built hashing algorithm
    * @param _message Signed message
    * @param _algorithm Hashing algorithm
    **/
    function hash(bytes _message, HashAlgorithm _algorithm)
        internal
        pure
        returns (bytes32 result)
    {
        if (_algorithm == HashAlgorithm.KECCAK256) {
            result = keccak256(_message);
        } else if (_algorithm == HashAlgorithm.SHA256) {
            result = sha256(_message);
        } else {
            result = ripemd160(_message);
        }
    }

    /**
    * @notice Verify ECDSA signature
    * @dev Uses one of pre built hashing algorithm
    * @param _message Signed message
    * @param _signature Signature of message hash
    * @param _publicKey secp256k1 public key
    * @param _algorithm Hashing algorithm
    **/
    function verify(bytes _message, bytes _signature, bytes _publicKey, HashAlgorithm _algorithm)
        internal
        pure
        returns (bool)
    {
        return toAddress(_publicKey) == recover(hash(_message, _algorithm), _signature);
    }
    

    function extendedKeccak (bytes _data) internal pure returns (bytes32, bytes32) {
        return (keccak256(abi.encodePacked(uint8(0x01), _data)),
                keccak256(abi.encodePacked(uint8(0x02), _data)));
    }

    function extendedKeccakToBN (bytes _data) internal pure returns (uint256) {

        bytes32 upper;
        bytes32 lower;

        (upper, lower) = (keccak256(abi.encodePacked(uint8(0x01), _data)),
                          keccak256(abi.encodePacked(uint8(0x02), _data)));

        uint256 delta = 0x14551231950b75fc4402da1732fc9bec0;
        uint256 n_minus_1 = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364140;

        uint256 upper_half = mulmod(uint256(upper), delta, n_minus_1);
        return 1 + addmod(upper_half, uint256(lower), n_minus_1);
    }

}

