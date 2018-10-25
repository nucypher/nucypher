pragma solidity ^0.4.25;


import "./lib/SignatureVerifier.sol";
import "./MinersEscrow.sol";


/**
* @notice Challenges for NuCypher net characters
* @dev TODO move or integrate with MinersEscrow
**/
contract ChallengeOverseer {

    uint256 constant PENALTY = 100; // TODO

    MinersEscrow public escrow;
    SignatureVerifier.HashAlgorithm public hashAlgorithm;
    mapping (bytes32 => bool) public challengedCFrags;

    /**
    * @param _escrow Escrow contract
    * @param _hashAlgorithm Hashing algorithm
    **/
    constructor(
        MinersEscrow _escrow,
        SignatureVerifier.HashAlgorithm _hashAlgorithm
    ) public {
        require(address(_escrow) != 0x0);
        escrow = _escrow;
        hashAlgorithm = _hashAlgorithm;
    }

    /**
    * @notice Submit proof that miner create wrong CFrag
    * @param _capsuleBytes Serialized capsule
    * @param _cFragBytes Serialized CFrag
    * @param _signature Signature of Capsule and CFrag
    * @param _minerPublicKey Miner's public key that was used to sign Capsule and CFrag
    * @param _minerPublicKeySignature Signature of public key by miner's eth-key
    **/
    function challengeCFrag(
        bytes _capsuleBytes,
        bytes _cFragBytes,
        bytes _signature,
        bytes _minerPublicKey,
        bytes _minerPublicKeySignature
    ) public {
        require(_minerPublicKey.length == 65);
        bytes memory signedData = abi.encodePacked(_capsuleBytes, _cFragBytes);

        // copy public key except first byte
        bytes memory preparedPublicKey = new bytes(64);
        assembly {
            let destination := add(preparedPublicKey, 32)
            let source := add(_minerPublicKey, 33)
            mstore(destination, mload(source))
            mstore(add(destination, 32), mload(add(source, 32)))
        }

        bytes32 dataHash = SignatureVerifier.hash(signedData, hashAlgorithm);
        require(SignatureVerifier.toAddress(preparedPublicKey) ==
            SignatureVerifier.recover(dataHash, _signature));
        require(!challengedCFrags[dataHash]); // CFrag is not challenged yet
        bytes32 publicKeyHash = SignatureVerifier.hash(_minerPublicKey, hashAlgorithm);
        address miner = SignatureVerifier.recover(publicKeyHash, _minerPublicKeySignature);

        require(escrow.getLockedTokens(miner) > 0); // TODO check that miner can be slashed
        if (!check(_capsuleBytes, _cFragBytes)) {
            escrow.slashMiner(miner, PENALTY);
        }
        challengedCFrags[dataHash] = true;
    }

    // TODO complete
    function check(
        bytes _capsuleBytes,
        bytes _cFragBytes
    ) public pure returns (bool) {
        return _capsuleBytes.length == 100 && _cFragBytes.length == 100; // just for tests
    }

}
