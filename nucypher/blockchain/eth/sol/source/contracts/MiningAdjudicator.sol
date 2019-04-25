pragma solidity ^0.5.3;

import "contracts/lib/ReEncryptionValidator.sol";
import "contracts/lib/SignatureVerifier.sol";
import "contracts/MinersEscrow.sol";
import "contracts/proxy/Upgradeable.sol";
import "zeppelin/math/SafeMath.sol";
import "zeppelin/math/Math.sol";


/**
* @notice Supervises miners' behavior and punishes when something's wrong.
**/
contract MiningAdjudicator is Upgradeable {

    using SafeMath for uint256;
    using UmbralDeserializer for bytes;

    event CFragEvaluated(
        bytes32 indexed evaluationHash,
        address indexed miner,
        address indexed investigator,
        bool correctness
    );

    // used only for upgrading
    bytes32 constant RESERVED_CAPSULE_AND_CFRAG_BYTES = bytes32(0);
    address constant RESERVED_ADDRESS = address(0);

    MinersEscrow public escrow;
    SignatureVerifier.HashAlgorithm public hashAlgorithm;
    uint256 public basePenalty;
    uint256 public penaltyHistoryCoefficient;
    uint256 public percentagePenaltyCoefficient;
    uint256 public rewardCoefficient;
    mapping (address => uint256) public penaltyHistory;
    mapping (bytes32 => bool) public evaluatedCFrags;

    /**
    * @param _escrow Escrow contract
    * @param _hashAlgorithm Hashing algorithm
    * @param _basePenalty Base for the penalty calculation
    * @param _penaltyHistoryCoefficient Coefficient for calculating the penalty depending on the history
    * @param _percentagePenaltyCoefficient Coefficient for calculating the percentage penalty
    * @param _rewardCoefficient Coefficient for calculating the reward
    **/
    constructor(
        MinersEscrow _escrow,
        SignatureVerifier.HashAlgorithm _hashAlgorithm,
        uint256 _basePenalty,
        uint256 _penaltyHistoryCoefficient,
        uint256 _percentagePenaltyCoefficient,
        uint256 _rewardCoefficient
    )
        public
    {
        // Sanity checks.
        require(_escrow.secondsPerPeriod() > 0 &&  // This contract has an escrow, and it's not the null address.
            // The reward and penalty coefficients are set.
            _percentagePenaltyCoefficient != 0 &&
            _rewardCoefficient != 0);
        escrow = _escrow;
        hashAlgorithm = _hashAlgorithm;
        basePenalty = _basePenalty;
        percentagePenaltyCoefficient = _percentagePenaltyCoefficient;
        penaltyHistoryCoefficient = _penaltyHistoryCoefficient;
        rewardCoefficient = _rewardCoefficient;
    }

    /**
    * @notice Submit proof that miner created wrong CFrag
    * @param _capsuleBytes Serialized capsule
    * @param _cFragBytes Serialized CFrag
    * @param _cFragSignature Signature of CFrag by miner
    * @param _taskSignature Signature of task specification by Bob
    * @param _requesterPublicKey Requester's public key that was used to sign Capsule
    * @param _minerPublicKey Miner's public key that was used to sign Capsule and CFrag
    * @param _minerPublicKeySignature Signature of public key by miner's eth-key
    * @param _preComputedData Pre computed data for CFrag correctness verification
    **/
    // TODO add way to slash owner of UserEscrow contract
    function evaluateCFrag(
        bytes memory _capsuleBytes,
        bytes memory _cFragBytes,
        bytes memory _cFragSignature,
        bytes memory _taskSignature,
        bytes memory _requesterPublicKey,
        bytes memory _minerPublicKey,
        bytes memory _minerPublicKeySignature,
        bytes memory _preComputedData
    )
        public
    {

        require(ReEncryptionValidator.checkSerializedCoordinates(_minerPublicKey),
                "Miner's public key is invalid");
        require(ReEncryptionValidator.checkSerializedCoordinates(_requesterPublicKey),
                "Requester's public key is invalid");

        // Check that CFrag is not evaluated yet
        bytes32 evaluationHash = SignatureVerifier.hash(
            abi.encodePacked(_capsuleBytes, _cFragBytes), hashAlgorithm);
        require(!evaluatedCFrags[evaluationHash], "This CFrag has already been evaluated.");

        UmbralDeserializer.PreComputedData memory precomp = _preComputedData.toPreComputedData();

        // Verify miner's signature of CFrag
        require(SignatureVerifier.verify(
                _cFragBytes,
                abi.encodePacked(_cFragSignature, precomp.lostBytes[1]),
                _minerPublicKey,
                hashAlgorithm),
                "CFrag signature is invalid"
        );

        // Verify miner's signature of taskSignature and that it corresponds to cfrag.proof.metadata
        UmbralDeserializer.CapsuleFrag memory cFrag = _cFragBytes.toCapsuleFrag();
        require(SignatureVerifier.verify(
                _taskSignature,
                abi.encodePacked(cFrag.proof.metadata, precomp.lostBytes[2]),
                _minerPublicKey,
                hashAlgorithm),
                "Task signature is invalid"
        );

        // Verify that _taskSignature is bob's signature of the task specification.
        // A task specification is: capsule + ursula pubkey + alice address + blockhash
        bytes32 miner_xcoord;
        assembly {
            miner_xcoord := mload(add(_minerPublicKey, 32))
        }
        require(SignatureVerifier.verify(
                abi.encodePacked(_capsuleBytes,
                                 precomp.lostBytes[4],
                                 miner_xcoord,
                                 precomp.alicesKeyAsAddress,
                                 bytes32(0)),
                abi.encodePacked(_taskSignature, precomp.lostBytes[3]),
                _requesterPublicKey,
                hashAlgorithm),
                "Specification signature is invalid"
        );

        // Extract miner's address and check that is real miner
        // TODO: This will depend on the outcome of #962
        address miner = SignatureVerifier.recover(
            SignatureVerifier.hash(_minerPublicKey, hashAlgorithm), _minerPublicKeySignature);
        // Check that miner can be slashed
        uint256 minerValue = escrow.getAllTokens(miner);
        require(minerValue > 0);

        // Verify correctness of re-encryption
        bool cfragIsCorrect = ReEncryptionValidator.validateCFrag(_capsuleBytes, _cFragBytes, _preComputedData);
        evaluatedCFrags[evaluationHash] = true;
        emit CFragEvaluated(evaluationHash, miner, msg.sender, cfragIsCorrect);
        if (!cfragIsCorrect) {
            (uint256 penalty, uint256 reward) = calculatePenaltyAndReward(miner, minerValue);
            escrow.slashMiner(miner, penalty, msg.sender, reward);
        }
    }

    /**
    * @notice Calculate penalty to the miner and reward to the investigator
    * @param _miner Miner's address
    * @param _minerValue Amount of tokens that belong to the miner
    **/
    function calculatePenaltyAndReward(address _miner, uint256 _minerValue)
        internal returns (uint256 penalty, uint256 reward)
    {
        penalty = basePenalty.add(penaltyHistoryCoefficient.mul(penaltyHistory[_miner]));
        penalty = Math.min(penalty, _minerValue.div(percentagePenaltyCoefficient));
        reward = penalty.div(rewardCoefficient);
        // TODO add maximum condition or other overflow protection or other penalty condition
        penaltyHistory[_miner] = penaltyHistory[_miner].add(1);
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `verifyState`
    function verifyState(address _testTarget) public {
        super.verifyState(_testTarget);
        require(address(delegateGet(_testTarget, "escrow()")) == address(escrow));
        require(SignatureVerifier.HashAlgorithm(delegateGet(_testTarget, "hashAlgorithm()")) == hashAlgorithm);
        require(delegateGet(_testTarget, "basePenalty()") == basePenalty);
        require(delegateGet(_testTarget, "penaltyHistoryCoefficient()") == penaltyHistoryCoefficient);
        require(delegateGet(_testTarget, "percentagePenaltyCoefficient()") == percentagePenaltyCoefficient);
        require(delegateGet(_testTarget, "rewardCoefficient()") == rewardCoefficient);
        require(delegateGet(_testTarget, "penaltyHistory(address)", bytes32(bytes20(RESERVED_ADDRESS))) ==
            penaltyHistory[RESERVED_ADDRESS]);
        bytes32 evaluationCFragHash = SignatureVerifier.hash(
            abi.encodePacked(RESERVED_CAPSULE_AND_CFRAG_BYTES), hashAlgorithm);
        require(delegateGet(_testTarget, "evaluatedCFrags(bytes32)", evaluationCFragHash) ==
            (evaluatedCFrags[evaluationCFragHash] ? 1 : 0));
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `finishUpgrade`
    function finishUpgrade(address _target) public {
        super.finishUpgrade(_target);
        MiningAdjudicator targetContract = MiningAdjudicator(_target);
        escrow = targetContract.escrow();
        hashAlgorithm = targetContract.hashAlgorithm();
        basePenalty = targetContract.basePenalty();
        penaltyHistoryCoefficient = targetContract.penaltyHistoryCoefficient();
        percentagePenaltyCoefficient = targetContract.percentagePenaltyCoefficient();
        rewardCoefficient = targetContract.rewardCoefficient();
        // preparation for the verifyState method
        bytes32 evaluationCFragHash = SignatureVerifier.hash(
            abi.encodePacked(RESERVED_CAPSULE_AND_CFRAG_BYTES), hashAlgorithm);
        evaluatedCFrags[evaluationCFragHash] = true;
        penaltyHistory[RESERVED_ADDRESS] = 123;
    }
}
