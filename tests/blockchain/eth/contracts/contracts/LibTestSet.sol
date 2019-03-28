pragma solidity ^0.5.3;


import "contracts/lib/SignatureVerifier.sol";
import "contracts/lib/UmbralDeserializer.sol";
import "contracts/lib/ReEncryptionValidator.sol";

/**
* @notice Contract for using SignatureVerifier library
**/
contract SignatureVerifierMock {

    function recover(bytes32 _hash, bytes memory _signature)
        public
        pure
        returns (address)
    {
        return SignatureVerifier.recover(_hash, _signature);
    }

    function toAddress(bytes memory _publicKey) public pure returns (address) {
        return SignatureVerifier.toAddress(_publicKey);
    }

    function hash(bytes memory _message, SignatureVerifier.HashAlgorithm _algorithm)
        public
        pure
        returns (bytes32 result)
    {
        return SignatureVerifier.hash(_message, _algorithm);
    }

    function verify(
        bytes memory _message,
        bytes memory _signature,
        bytes memory _publicKey,
        SignatureVerifier.HashAlgorithm _algorithm
    )
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
            bytes memory kFragSignature,
            bytes memory metadata
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

    // `toCapsuleFrag` is split into two methods because of EVM stack problems with many variables
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
            bytes memory kFragSignature,
            bytes memory metadata
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


/**
* @notice Contract for using ReEncryptionValidator library
**/
contract ReEncryptionValidatorMock {

    using UmbralDeserializer for bytes;

//    uint8 public constant UMBRAL_PARAMETER_U_SIGN = ReEncryptionValidator.UMBRAL_PARAMETER_U_SIGN();
//    uint256 public constant UMBRAL_PARAMETER_U_XCOORD = ReEncryptionValidator.UMBRAL_PARAMETER_U_XCOORD();
//    uint256 public constant UMBRAL_PARAMETER_U_YCOORD = ReEncryptionValidator.UMBRAL_PARAMETER_U_YCOORD();

//    uint256 constant FIELD_ORDER = ReEncryptionValidator.FIELD_ORDER;
//    uint256 constant MINUS_2 = ReEncryptionValidator.MINUS_2;
//    uint256 constant MINUS_ONE_HALF = ReEncryptionValidator.MINUS_ONE_HALF

    function validateCFrag(
        bytes memory _capsuleBytes,
        bytes memory _cFragBytes,
        bytes memory _precomputedBytes
    )
        public pure returns (bool)
    {
        return ReEncryptionValidator.validateCFrag(_capsuleBytes, _cFragBytes, _precomputedBytes);
    }

    function computeProofChallengeScalar(
        bytes memory _capsuleBytes,
        bytes memory _cFragBytes
    )
        public pure returns (uint256)
    {
        return ReEncryptionValidator.computeProofChallengeScalar(_capsuleBytes, _cFragBytes);
    }

    function aliceAddress(
        bytes memory _cFragBytes,
        bytes memory _precomputedBytes
    )
        public pure returns (address)
    {
        return ReEncryptionValidator.aliceAddress(_cFragBytes, _precomputedBytes);
    }

    function extendedKeccakToBN (bytes memory _data) public pure returns (uint256) {
        return ReEncryptionValidator.extendedKeccakToBN(_data);
    }

	function check_compressed_point(
		uint8 _pointSign,
		uint256 _pointX,
		uint256 _pointY
	) public pure returns(bool) {
        return ReEncryptionValidator.check_compressed_point(_pointSign, _pointX, _pointY);
	}

    function is_on_curve(uint256 Px, uint256 Py) public pure returns (bool) {
        return ReEncryptionValidator.is_on_curve(Px, Py);
    }

    function ecmulVerify(
    	uint256 x1,
    	uint256 y1,
    	uint256 scalar,
    	uint256 qx,
    	uint256 qy
    ) public pure returns(bool) {
        return ReEncryptionValidator.ecmulVerify(x1, y1, scalar, qx, qy);
	}

    function eqAffineJacobian(
    	uint256[2] memory P,
    	uint256[3] memory Q
    ) public pure returns(bool){
        return ReEncryptionValidator.eqAffineJacobian(P, Q);
    }

    function addAffineJacobian(
    	uint[2] memory P,
    	uint[2] memory Q
    ) public pure returns (uint[3] memory) {
        return ReEncryptionValidator.addAffineJacobian(P, Q);
    }

    function doubleJacobian(uint[3] memory P) internal pure returns (uint[3] memory) {
        return ReEncryptionValidator.doubleJacobian(P);
    }
}
