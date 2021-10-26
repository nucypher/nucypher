// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "contracts/lib/ReEncryptionValidator.sol";
import "contracts/lib/SignatureVerifier.sol";
import "zeppelin/math/Math.sol";
import "zeppelin/math/SafeCast.sol";


/**
* @title Adjudicator
* @notice Supervises operators' behavior and punishes when something's wrong.
* @dev |v3.1.1|
*/
abstract contract Adjudicator {

    using UmbralDeserializer for bytes;
    using SafeCast for uint256;

    event CFragEvaluated(
        bytes32 indexed evaluationHash,
        address indexed investigator,
        bool correctness
    );
    event IncorrectCFragVerdict(
        bytes32 indexed evaluationHash,
        address indexed operator
    );

    // used only for upgrading
    bytes32 constant RESERVED_CAPSULE_AND_CFRAG_BYTES = bytes32(0);
    address constant RESERVED_ADDRESS = address(0);

    SignatureVerifier.HashAlgorithm public immutable hashAlgorithm;
    uint256 public immutable basePenalty;
    uint256 public immutable penaltyHistoryCoefficient;
    uint256 public immutable percentagePenaltyCoefficient;

    mapping (address => uint256) public penaltyHistory;
    mapping (bytes32 => bool) public evaluatedCFrags;

    // TODO add slots

    /**
    * @param _hashAlgorithm Hashing algorithm
    * @param _basePenalty Base for the penalty calculation
    * @param _penaltyHistoryCoefficient Coefficient for calculating the penalty depending on the history
    * @param _percentagePenaltyCoefficient Coefficient for calculating the percentage penalty
    */
    constructor(
        SignatureVerifier.HashAlgorithm _hashAlgorithm,
        uint256 _basePenalty,
        uint256 _penaltyHistoryCoefficient,
        uint256 _percentagePenaltyCoefficient
    ) {
        // Sanity checks.
        require(// The reward and penalty coefficients are set.
            _percentagePenaltyCoefficient != 0);
        hashAlgorithm = _hashAlgorithm;
        basePenalty = _basePenalty;
        percentagePenaltyCoefficient = _percentagePenaltyCoefficient;
        penaltyHistoryCoefficient = _penaltyHistoryCoefficient;
    }

    /**
    * @notice Submit proof that a operator created wrong CFrag
    * @param _capsuleBytes Serialized capsule
    * @param _cFragBytes Serialized CFrag
    * @param _cFragSignature Signature of CFrag by operator
    * @param _taskSignature Signature of task specification by Bob
    * @param _requesterPublicKey Bob's signing public key, also known as "stamp"
    * @param _operatorPublicKey Operator's signing public key, also known as "stamp"
    * @param _operatorIdentityEvidence Signature of operator's public key by operator's eth-key
    * @param _preComputedData Additional pre-computed data for CFrag correctness verification
    */
    function evaluateCFrag(
        bytes memory _capsuleBytes,
        bytes memory _cFragBytes,
        bytes memory _cFragSignature,
        bytes memory _taskSignature,
        bytes memory _requesterPublicKey,
        bytes memory _operatorPublicKey,
        bytes memory _operatorIdentityEvidence,
        bytes memory _preComputedData
    )
        public
    {
        // 1. Check that CFrag is not evaluated yet
        bytes32 evaluationHash = SignatureVerifier.hash(
            abi.encodePacked(_capsuleBytes, _cFragBytes), hashAlgorithm);
        require(!evaluatedCFrags[evaluationHash], "This CFrag has already been evaluated.");
        evaluatedCFrags[evaluationHash] = true;

        // 2. Verify correctness of re-encryption
        bool cFragIsCorrect = ReEncryptionValidator.validateCFrag(_capsuleBytes, _cFragBytes, _preComputedData);
        emit CFragEvaluated(evaluationHash, msg.sender, cFragIsCorrect);

        // 3. Verify associated public keys and signatures
        require(ReEncryptionValidator.checkSerializedCoordinates(_operatorPublicKey),
                "Operator's public key is invalid");
        require(ReEncryptionValidator.checkSerializedCoordinates(_requesterPublicKey),
                "Requester's public key is invalid");

        UmbralDeserializer.PreComputedData memory precomp = _preComputedData.toPreComputedData();

        // Verify operator's signature of CFrag
        require(SignatureVerifier.verify(
                _cFragBytes,
                abi.encodePacked(_cFragSignature, precomp.lostBytes[1]),
                _operatorPublicKey,
                hashAlgorithm),
                "CFrag signature is invalid"
        );

        // Verify operator's signature of taskSignature and that it corresponds to cfrag.proof.metadata
        UmbralDeserializer.CapsuleFrag memory cFrag = _cFragBytes.toCapsuleFrag();
        require(SignatureVerifier.verify(
                _taskSignature,
                abi.encodePacked(cFrag.proof.metadata, precomp.lostBytes[2]),
                _operatorPublicKey,
                hashAlgorithm),
                "Task signature is invalid"
        );

        // Verify that _taskSignature is bob's signature of the task specification.
        // A task specification is: capsule + ursula pubkey + alice address + blockhash
        bytes32 stampXCoord;
        assembly {
            stampXCoord := mload(add(_operatorPublicKey, 32))
        }
        bytes memory stamp = abi.encodePacked(precomp.lostBytes[4], stampXCoord);

        require(SignatureVerifier.verify(
                abi.encodePacked(_capsuleBytes,
                                 stamp,
                                 _operatorIdentityEvidence,
                                 precomp.alicesKeyAsAddress,
                                 bytes32(0)),
                abi.encodePacked(_taskSignature, precomp.lostBytes[3]),
                _requesterPublicKey,
                hashAlgorithm),
                "Specification signature is invalid"
        );

        // 4. Extract operator address from stamp signature.
        address operator = SignatureVerifier.recover(
            SignatureVerifier.hashEIP191(stamp, bytes1(0x45)), // Currently, we use version E (0x45) of EIP191 signatures
            _operatorIdentityEvidence);

        // 5. Check that operator can be slashed
        uint96 operatorValue = authorizedStake(operator);
        require(operatorValue > 0, "Operator has no tokens");

        // 6. If CFrag was incorrect, slash operator
        if (!cFragIsCorrect) {
            uint96 penalty = calculatePenalty(operator, operatorValue);
            slash(operator, penalty, msg.sender);
            emit IncorrectCFragVerdict(evaluationHash, operator);
        }
    }

    /**
    * @notice Calculate penalty to the operator
    * @param _operator Operator's address
    * @param _operatorValue Amount of tokens that belong to the operator
    */
    function calculatePenalty(address _operator, uint96 _operatorValue)
        internal returns (uint96)
    {
        uint256 penalty = basePenalty + penaltyHistoryCoefficient * penaltyHistory[_operator];
        penalty = Math.min(penalty, _operatorValue / percentagePenaltyCoefficient);
        // TODO add maximum condition or other overflow protection or other penalty condition (#305?)
        penaltyHistory[_operator] = penaltyHistory[_operator] + 1;
        return penalty.toUint96();
    }

    /**
    * @notice Get all tokens delegated to the operator
    */
    function authorizedStake(address _operator) public virtual view returns (uint96);

    /**
    * @notice Slash the operator's stake and reward the investigator
    * @param _operator Operator's address
    * @param _penalty Penalty
    * @param _investigator Investigator
    */
    function slash(
        address _operator,
        uint96 _penalty,
        address _investigator
    ) internal virtual;

//    function verifyAdjudicatorState(address _testTarget) public virtual {
//        bytes32 evaluationCFragHash = SignatureVerifier.hash(
//            abi.encodePacked(RESERVED_CAPSULE_AND_CFRAG_BYTES), SignatureVerifier.HashAlgorithm.SHA256);
//        require(Getters.delegateGet(_testTarget, this.evaluatedCFrags.selector, evaluationCFragHash) ==
//            (evaluatedCFrags[evaluationCFragHash] ? 1 : 0));
//        require(Getters.delegateGet(_testTarget, this.penaltyHistory.selector, bytes32(bytes20(RESERVED_ADDRESS))) ==
//            penaltyHistory[RESERVED_ADDRESS]);
//    }
//
//    function finishAdjudicatorUpgrade(address _target) public virtual {
//        // preparation for the verifyState method
//        bytes32 evaluationCFragHash = SignatureVerifier.hash(
//            abi.encodePacked(RESERVED_CAPSULE_AND_CFRAG_BYTES), SignatureVerifier.HashAlgorithm.SHA256);
//        evaluatedCFrags[evaluationCFragHash] = true;
//        penaltyHistory[RESERVED_ADDRESS] = 123;
//    }

}
