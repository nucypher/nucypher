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

}