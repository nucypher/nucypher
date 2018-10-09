pragma solidity ^0.4.25;


import "contracts/lib/SignatureVerifier.sol";


/**
* @notice Contract for using SignatureVerifier library
**/
contract SignatureVerifierMock {

    function recover(bytes32 _hash, bytes _signature)
        public
        pure
        returns (address)
    {
        return SignatureVerifier.recover(_hash, _signature);
    }

    function toAddress(bytes _publicKey) public pure returns (address) {
        return SignatureVerifier.toAddress(_publicKey);
    }

    function verify(bytes _message, bytes _signature, bytes _publicKey, SignatureVerifier.HashAlgorithm _algorithm)
        public
        pure
        returns (bool)
    {
        return SignatureVerifier.verify(_message, _signature, _publicKey, _algorithm);
    }

}