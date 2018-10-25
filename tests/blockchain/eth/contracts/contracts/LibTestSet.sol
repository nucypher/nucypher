pragma solidity ^0.4.25;


import "contracts/lib/SignatureVerifier.sol";
import "contracts/lib/UmbralDeserializer.sol";


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

    function hash(bytes _message, SignatureVerifier.HashAlgorithm _algorithm)
        public
        pure
        returns (bytes32 result)
    {
        return SignatureVerifier.hash(_message, _algorithm);
    }

    function verify(bytes _message, bytes _signature, bytes _publicKey, SignatureVerifier.HashAlgorithm _algorithm)
        public
        pure
        returns (bool)
    {
        return SignatureVerifier.verify(_message, _signature, _publicKey, _algorithm);
    }

}


/**
* @dev Contract for testing UmbralDeserializer library
**/
contract UmbralDeserializerMock {
    using UmbralDeserializer for bytes;


    function toOriginalCapsule(bytes memory _capsuleBytes)
        public pure returns (bytes memory pointE, bytes memory pointV, bytes32 bnSig)
    {
        UmbralDeserializer.OriginalCapsule memory capsule = _capsuleBytes.toOriginalCapsule();
        pointE = capsule.pointE;
        pointV = capsule.pointV;
        bnSig = capsule.bnSig;
    }

    function toCorrectnessProof(bytes memory _proofBytes)
        public pure returns (
            bytes pointE2,
            bytes pointV2,
            bytes pointKFragCommitment,
            bytes pointKFragPok,
            bytes32 bnSig,
            bytes kFragSignature,
            bytes metadata
        )
    {
        UmbralDeserializer.CorrectnessProof memory proof = _proofBytes.toCorrectnessProof();
        pointE2 = proof.pointE2;
        pointV2 = proof.pointV2;
        pointKFragCommitment = proof.pointKFragCommitment;
        pointKFragPok = proof.pointKFragPok;
        bnSig = proof.bnSig;
        kFragSignature = proof.kFragSignature;
        metadata = proof.metadata;
    }

    // `toCapsuleFrag` is splitted into two methods because of EVM stack problems with many variables
    function toCorrectnessProofFromCapsuleFrag(bytes memory _cFragBytes)
        public pure returns (
            bytes pointE2,
            bytes pointV2,
            bytes pointKFragCommitment,
            bytes pointKFragPok,
            bytes32 bnSig,
            bytes kFragSignature,
            bytes metadata
        )
    {
        UmbralDeserializer.CapsuleFrag memory cFrag = _cFragBytes.toCapsuleFrag();
        UmbralDeserializer.CorrectnessProof memory proof = cFrag.proof;
        pointE2 = proof.pointE2;
        pointV2 = proof.pointV2;
        pointKFragCommitment = proof.pointKFragCommitment;
        pointKFragPok = proof.pointKFragPok;
        bnSig = proof.bnSig;
        kFragSignature = proof.kFragSignature;
        metadata = proof.metadata;
    }

    function toCapsuleFrag(bytes memory _cFragBytes)
        public pure returns (
            bytes pointE1,
            bytes pointV1,
            bytes32 kFragId,
            bytes pointNonInteractive,
            bytes pointXCoord
        )
    {
        UmbralDeserializer.CapsuleFrag memory cFrag = _cFragBytes.toCapsuleFrag();
        pointE1 = cFrag.pointE1;
        pointV1 = cFrag.pointV1;
        kFragId = cFrag.kFragId;
        pointNonInteractive = cFrag.pointNonInteractive;
        pointXCoord = cFrag.pointXCoord;
    }
}