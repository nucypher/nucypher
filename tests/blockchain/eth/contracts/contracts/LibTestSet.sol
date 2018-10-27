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

    function toCapsule(bytes memory _capsuleBytes)
        public pure returns (
            byte pointESign,
            bytes32 pointEXCoord,
            byte pointVSign,
            bytes32 pointVXCoord,
            bytes32 bnSig
        )
    {
        UmbralDeserializer.Capsule memory capsule = _capsuleBytes.toCapsule();
        pointESign = byte(capsule.pointE.sign);
        pointEXCoord = bytes32(capsule.pointE.xCoord);
        pointVSign = byte(capsule.pointV.sign);
        pointVXCoord = bytes32(capsule.pointV.xCoord);
        bnSig = bytes32(capsule.bnSig);
    }

    function toCorrectnessProof(bytes memory _proofBytes)
        public pure returns (
            byte pointE2Sign,
            bytes32 pointE2XCoord,
            byte pointV2Sign,
            bytes32 pointV2XCoord,
            byte pointKFragCommitmentSign,
            bytes32 pointKFragCommitmentXCoord,
            byte pointKFragPokSign,
            bytes32 pointKFragPokXCoord,
            bytes32 bnSig,
            bytes kFragSignature,
            bytes metadata
        )
    {
        UmbralDeserializer.CorrectnessProof memory proof = _proofBytes.toCorrectnessProof();
        pointE2Sign = byte(proof.pointE2.sign);
        pointE2XCoord = bytes32(proof.pointE2.xCoord);
        pointV2Sign = byte(proof.pointV2.sign);
        pointV2XCoord = bytes32(proof.pointV2.xCoord);
        pointKFragCommitmentSign = byte(proof.pointKFragCommitment.sign);
        pointKFragCommitmentXCoord = bytes32(proof.pointKFragCommitment.xCoord);
        pointKFragPokSign = byte(proof.pointKFragPok.sign);
        pointKFragPokXCoord = bytes32(proof.pointKFragPok.xCoord);
        bnSig = bytes32(proof.bnSig);
        kFragSignature = proof.kFragSignature;
        metadata = proof.metadata;
    }

    // `toCapsuleFrag` is splitted into two methods because of EVM stack problems with many variables
    function toCorrectnessProofFromCapsuleFrag(bytes memory _cFragBytes)
        public pure returns (
            byte pointE2Sign,
            bytes32 pointE2XCoord,
            byte pointV2Sign,
            bytes32 pointV2XCoord,
            byte pointKFragCommitmentSign,
            bytes32 pointKFragCommitmentXCoord,
            byte pointKFragPokSign,
            bytes32 pointKFragPokXCoord,
            bytes32 bnSig,
            bytes kFragSignature,
            bytes metadata
        )
    {
        UmbralDeserializer.CapsuleFrag memory cFrag = _cFragBytes.toCapsuleFrag();
        UmbralDeserializer.CorrectnessProof memory proof = cFrag.proof;
        pointE2Sign = byte(proof.pointE2.sign);
        pointE2XCoord = bytes32(proof.pointE2.xCoord);
        pointV2Sign = byte(proof.pointV2.sign);
        pointV2XCoord = bytes32(proof.pointV2.xCoord);
        pointKFragCommitmentSign = byte(proof.pointKFragCommitment.sign);
        pointKFragCommitmentXCoord = bytes32(proof.pointKFragCommitment.xCoord);
        pointKFragPokSign = byte(proof.pointKFragPok.sign);
        pointKFragPokXCoord = bytes32(proof.pointKFragPok.xCoord);
        bnSig = bytes32(proof.bnSig);
        kFragSignature = proof.kFragSignature;
        metadata = proof.metadata;
    }

    function toCapsuleFrag(bytes memory _cFragBytes)
        public pure returns (
            byte pointE1Sign,
            bytes32 pointE1XCoord,
            byte pointV1Sign,
            bytes32 pointV1XCoord,
            bytes32 kFragId,
            byte pointPrecursorSign,
            bytes32 pointPrecursorXCoord
        )
    {
        UmbralDeserializer.CapsuleFrag memory cFrag = _cFragBytes.toCapsuleFrag();
        pointE1Sign = byte(cFrag.pointE1.sign);
        pointE1XCoord = bytes32(cFrag.pointE1.xCoord);
        pointV1Sign = byte(cFrag.pointV1.sign);
        pointV1XCoord = bytes32(cFrag.pointV1.xCoord);
        kFragId = cFrag.kFragId;
        pointPrecursorSign = byte(cFrag.pointPrecursor.sign);
        pointPrecursorXCoord = bytes32(cFrag.pointPrecursor.xCoord);
    }
}