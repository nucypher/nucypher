pragma solidity ^0.4.25;


import "contracts/lib/UmbralDeserializer.sol";
import "contracts/lib/SignatureVerifier.sol";
import "contracts/lib/Numerology.sol";
import "contracts/MinersEscrow.sol";
import "contracts/proxy/Upgradeable.sol";
import "zeppelin/math/SafeMath.sol";
import "zeppelin/math/Math.sol";


/**
* @notice Supervises miners' behavior and punishes when something's wrong.
**/
contract MiningAdjudicator is Upgradeable {
    using UmbralDeserializer for bytes;
    using SafeMath for uint256;

    event CFragEvaluated(
        bytes32 indexed evaluationHash,
        address indexed miner,
        address indexed investigator,
        bool correctness
    );

    uint8 public constant UMBRAL_PARAMETER_U_SIGN = 0x02;
    uint256 public constant UMBRAL_PARAMETER_U_XCOORD = 0x03c98795773ff1c241fc0b1cced85e80f8366581dda5c9452175ebd41385fa1f;
    uint256 public constant UMBRAL_PARAMETER_U_YCOORD = 0x7880ed56962d7c0ae44d6f14bb53b5fe64b31ea44a41d0316f3a598778f0f936;
    // used only for upgrading
    bytes32 constant RESERVED_CAPSULE_AND_CFRAG_BYTES = bytes32(0);
    address constant RESERVED_ADDRESS = 0x0;

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
        require(address(_escrow) != 0x0 &&
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
    * @param _capsuleSignatureByRequester Signature of Capsule by requester
    * @param _capsuleSignatureByRequesterAndMiner Signature of Capsule by requester and miner
    * @param _cFragBytes Serialized CFrag
    * @param _cFragSignatureByMiner Signature of CFrag by miner
    * @param _requesterPublicKey Requester's public key that was used to sign Capsule
    * @param _minerPublicKey Miner's public key that was used to sign Capsule and CFrag
    * @param _minerPublicKeySignature Signature of public key by miner's eth-key
    * @param _preComputedData Pre computed data for CFrag correctness verification
    **/
    // TODO add way to slash owner of UserEscrow contract
    function evaluateCFrag(
        bytes _capsuleBytes,
        bytes _capsuleSignatureByRequester,
        bytes _capsuleSignatureByRequesterAndMiner,
        bytes _cFragBytes,
        bytes _cFragSignatureByMiner,
        bytes _requesterPublicKey,
        bytes _minerPublicKey,
        bytes _minerPublicKeySignature,
        bytes _preComputedData
    )
        public
    {
        require(_minerPublicKey.length == 65 && _requesterPublicKey.length == 65);

        // Check that CFrag is not evaluated yet
        bytes32 evaluationHash = SignatureVerifier.hash(
            abi.encodePacked(_capsuleBytes, _cFragBytes), hashAlgorithm);
        require(!evaluatedCFrags[evaluationHash]);

        // Verify requester's signature of Capsule
        bytes memory preparedPublicKey = new bytes(64);
        preparePublicKey(preparedPublicKey, _requesterPublicKey);
        require(SignatureVerifier.verify(
                _capsuleBytes, _capsuleSignatureByRequester, preparedPublicKey, hashAlgorithm));

        // Verify miner's signatures of capsule and CFrag
        preparePublicKey(preparedPublicKey, _minerPublicKey);
        require(SignatureVerifier.verify(
                _capsuleSignatureByRequester, _capsuleSignatureByRequesterAndMiner, preparedPublicKey, hashAlgorithm));
        require(SignatureVerifier.verify(
                _cFragBytes, _cFragSignatureByMiner, preparedPublicKey, hashAlgorithm));

        // Extract miner's address and check that is real miner
        address miner = SignatureVerifier.recover(
            SignatureVerifier.hash(_minerPublicKey, hashAlgorithm), _minerPublicKeySignature);
        // Check that miner can be slashed
        (uint256 minerValue,,,) = escrow.minerInfo(miner);
        require(minerValue > 0);

        // Verify correctness of re-encryption
        evaluatedCFrags[evaluationHash] = true;
        if (!isCapsuleFragCorrect(_capsuleBytes, _cFragBytes, _preComputedData)) {
            (uint256 penalty, uint256 reward) = calculatePenaltyAndReward(miner, minerValue);
            escrow.slashMiner(miner, penalty, msg.sender, reward);
            emit CFragEvaluated(evaluationHash, miner, msg.sender, false);
        } else {
            emit CFragEvaluated(evaluationHash, miner, msg.sender, true);
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
        penalty = Math.min256(penalty, _minerValue.div(percentagePenaltyCoefficient));
        reward = penalty.div(rewardCoefficient);
        // TODO add maximum condition or other overflow protection or other penalty condition
        penaltyHistory[_miner] = penaltyHistory[_miner].add(1);
    }

    /**
    * @notice Prepare public key before verification (cut the first byte)
    **/
    function preparePublicKey(bytes memory _preparedPublicKey, bytes memory _publicKey)
        public pure
    {
        assembly {
            let destination := add(_preparedPublicKey, 32) // skip array length
            let source := add(_publicKey, 33) // skip array length and first byte in the array
            mstore(destination, mload(source))
            mstore(add(destination, 32), mload(add(source, 32)))
        }
    }



    function aliceAddress(
        bytes memory _cFragBytes,
        bytes memory _precomputedBytes
    )
        public pure
        returns (address)
    {
        UmbralDeserializer.CapsuleFrag memory _cFrag = _cFragBytes.toCapsuleFrag();
        UmbralDeserializer.PreComputedData memory _precomputed = _precomputedBytes.toPreComputedData();

        // Extract Alice's address and check that it corresponds to the one provided
        address alicesAddress = SignatureVerifier.recover(
            _precomputed.hashedKFragValidityMessage,
            abi.encodePacked(_cFrag.proof.kFragSignature, _precomputed.kfragSignatureV)
        );
        return alicesAddress;
    }

    /**
    * @notice Check correctness of re-encryption
    * @param _capsuleBytes Capsule
    * @param _cFragBytes Capsule frag
    * @param _precomputedBytes Additional precomputed data
    **/
    function isCapsuleFragCorrect(
        bytes memory _capsuleBytes,
        bytes memory _cFragBytes,
        bytes memory _precomputedBytes
    )
        public pure returns (bool)
    {
        UmbralDeserializer.Capsule memory _capsule = _capsuleBytes.toCapsule();
        UmbralDeserializer.CapsuleFrag memory _cFrag = _cFragBytes.toCapsuleFrag();
        UmbralDeserializer.PreComputedData memory _precomputed = _precomputedBytes.toPreComputedData();

        // Extract Alice's address and check that it corresponds to the one provided
        address alicesAddress = SignatureVerifier.recover(
            _precomputed.hashedKFragValidityMessage,
            abi.encodePacked(_cFrag.proof.kFragSignature, _precomputed.kfragSignatureV)
        );
        require(alicesAddress == _precomputed.alicesKeyAsAddress, "Bad KFrag signature");


        uint256 h = computeProofChallengeScalar(_capsuleBytes, _cFragBytes);

        //////
        // Verifying equation: z*E == h*E_1 + E_2
        //////

        // Input validation: E
        require(Numerology.check_compressed_point(
            _capsule.pointE.sign,
            _capsule.pointE.xCoord,
            _precomputed.pointEyCoord
        ));

        // Input validation: z*E
        require(Numerology.is_on_curve(_precomputed.pointEZxCoord, _precomputed.pointEZyCoord));
        bool left_hand_element_is_correct = Numerology.ecmulVerify(
            _capsule.pointE.xCoord,     // E_x
            _precomputed.pointEyCoord,  // E_y
            _cFrag.proof.bnSig,         // z
            _precomputed.pointEZxCoord, // zE_x
            _precomputed.pointEZyCoord  // zE_y
        );

        // Input validation: E1
        require(Numerology.check_compressed_point(
            _cFrag.pointE1.sign,        // E1_sign
            _cFrag.pointE1.xCoord,      // E1_x
            _precomputed.pointE1yCoord  // E1_y
        ));

        // Input validation: h*E_1
        require(Numerology.is_on_curve(_precomputed.pointE1HxCoord, _precomputed.pointE1HyCoord));
        bool rhs_element_is_correct = Numerology.ecmulVerify(
            _cFrag.pointE1.xCoord,          // E1_x
            _precomputed.pointE1yCoord,     // E1_y
            h,
            _precomputed.pointE1HxCoord,    // hE1_x
            _precomputed.pointE1HyCoord     // hE1_y
        );

        // Input validation: E_2
        require(Numerology.check_compressed_point(
            _cFrag.proof.pointE2.sign,        // E2_sign
            _cFrag.proof.pointE2.xCoord,      // E2_x
            _precomputed.pointE2yCoord        // E2_y
        ));

        bool equation_holds = Numerology.eqAffineJacobian(
            [_precomputed.pointEZxCoord,  _precomputed.pointEZyCoord],
            Numerology.addAffineJacobian(
                [_cFrag.proof.pointE2.xCoord, _precomputed.pointE2yCoord],
                [_precomputed.pointE1HxCoord, _precomputed.pointE1HyCoord]
            )
        );

        if (!(left_hand_element_is_correct && rhs_element_is_correct && equation_holds)){
            return false;
        }

        //////
        // Verifying equation: z*V == h*V_1 + V_2
        //////

        // Input validation: V
        require(Numerology.check_compressed_point(
            _capsule.pointV.sign,
            _capsule.pointV.xCoord,
            _precomputed.pointVyCoord
        ));

        // Input validation: z*V
        require(Numerology.is_on_curve(_precomputed.pointVZxCoord, _precomputed.pointVZyCoord));
        left_hand_element_is_correct = Numerology.ecmulVerify(
            _capsule.pointV.xCoord,     // V_x
            _precomputed.pointVyCoord,  // V_y
            _cFrag.proof.bnSig,         // z
            _precomputed.pointVZxCoord, // zV_x
            _precomputed.pointVZyCoord  // zV_y
        );

        // Input validation: V1
        require(Numerology.check_compressed_point(
            _cFrag.pointV1.sign,        // V1_sign
            _cFrag.pointV1.xCoord,      // V1_x
            _precomputed.pointV1yCoord  // V1_y
        ));

        // Input validation: h*V_1
        require(Numerology.is_on_curve(_precomputed.pointV1HxCoord, _precomputed.pointV1HyCoord));
        rhs_element_is_correct = Numerology.ecmulVerify(
            _cFrag.pointV1.xCoord,          // V1_x
            _precomputed.pointV1yCoord,     // V1_y
            h,
            _precomputed.pointV1HxCoord,    // h*V1_x
            _precomputed.pointV1HyCoord     // h*V1_y
        );

        // Input validation: V_2
        require(Numerology.check_compressed_point(
            _cFrag.proof.pointV2.sign,        // V2_sign
            _cFrag.proof.pointV2.xCoord,      // V2_x
            _precomputed.pointV2yCoord        // V2_y
        ));

        equation_holds = Numerology.eqAffineJacobian(
            [_precomputed.pointVZxCoord,  _precomputed.pointVZyCoord],
            Numerology.addAffineJacobian(
                [_cFrag.proof.pointV2.xCoord, _precomputed.pointV2yCoord],
                [_precomputed.pointV1HxCoord, _precomputed.pointV1HyCoord]
            )
        );

        if (!(left_hand_element_is_correct && rhs_element_is_correct && equation_holds)){
            return false;
        }

        //////
        // Verifying equation: z*U == h*U_1 + U_2
        //////

        // We don't have to validate U since it's fixed and hard-coded

        // Input validation: z*U
        require(Numerology.is_on_curve(_precomputed.pointUZxCoord, _precomputed.pointUZyCoord));
        left_hand_element_is_correct = Numerology.ecmulVerify(
            UMBRAL_PARAMETER_U_XCOORD,  // U_x
            UMBRAL_PARAMETER_U_YCOORD,  // U_y
            _cFrag.proof.bnSig,         // z
            _precomputed.pointUZxCoord, // zU_x
            _precomputed.pointUZyCoord  // zU_y
        );

        // Input validation: U_1  (a.k.a. KFragCommitment)
        require(Numerology.check_compressed_point(
            _cFrag.proof.pointKFragCommitment.sign,     // U1_sign
            _cFrag.proof.pointKFragCommitment.xCoord,   // U1_x
            _precomputed.pointU1yCoord                  // U1_y
        ));

        // Input validation: h*U_1
        require(Numerology.is_on_curve(_precomputed.pointU1HxCoord, _precomputed.pointU1HyCoord));
        rhs_element_is_correct = Numerology.ecmulVerify(
            _cFrag.proof.pointKFragCommitment.xCoord,   // U1_x
            _precomputed.pointU1yCoord,                 // U1_y
            h,
            _precomputed.pointU1HxCoord,    // h*V1_x
            _precomputed.pointU1HyCoord     // h*V1_y
        );

        // Input validation: U_2  (a.k.a. KFragPok ("proof of knowledge"))
        require(Numerology.check_compressed_point(
            _cFrag.proof.pointKFragPok.sign,    // U2_sign
            _cFrag.proof.pointKFragPok.xCoord,  // U2_x
            _precomputed.pointU2yCoord          // U2_y
        ));

        equation_holds = Numerology.eqAffineJacobian(
            [_precomputed.pointUZxCoord,  _precomputed.pointUZyCoord],
            Numerology.addAffineJacobian(
                [_cFrag.proof.pointKFragPok.xCoord, _precomputed.pointU2yCoord],
                [_precomputed.pointU1HxCoord, _precomputed.pointU1HyCoord]
            )
        );

        return left_hand_element_is_correct && rhs_element_is_correct && equation_holds;
    }


    function computeProofChallengeScalar(
        bytes memory _capsuleBytes,
        bytes memory _cFragBytes
    ) public pure returns (uint256) {

        UmbralDeserializer.Capsule memory _capsule = _capsuleBytes.toCapsule();
        UmbralDeserializer.CapsuleFrag memory _cFrag = _cFragBytes.toCapsuleFrag();

        // Compute h = hash_to_bignum(e, e1, e2, v, v1, v2, u, u1, u2, metadata)
        bytes memory hashInput = abi.encodePacked(
            // Point E
            _capsule.pointE.sign,
            _capsule.pointE.xCoord,
            // Point E1
            _cFrag.pointE1.sign,
            _cFrag.pointE1.xCoord,
            // Point E2
            _cFrag.proof.pointE2.sign,
            _cFrag.proof.pointE2.xCoord
        );

        hashInput = abi.encodePacked(
            hashInput,
            // Point V
            _capsule.pointV.sign,
            _capsule.pointV.xCoord,
            // Point V1
            _cFrag.pointV1.sign,
            _cFrag.pointV1.xCoord,
            // Point V2
            _cFrag.proof.pointV2.sign,
            _cFrag.proof.pointV2.xCoord
        );

        hashInput = abi.encodePacked(
            hashInput,
            // Point U
            bytes1(UMBRAL_PARAMETER_U_SIGN),
            bytes32(UMBRAL_PARAMETER_U_XCOORD),
            // Point U1
            _cFrag.proof.pointKFragCommitment.sign,
            _cFrag.proof.pointKFragCommitment.xCoord,
            // Point U2
            _cFrag.proof.pointKFragPok.sign,
            _cFrag.proof.pointKFragPok.xCoord,
            // Re-encryption metadata
            _cFrag.proof.metadata
        );

        uint256 h = extendedKeccakToBN(hashInput);
        return h;

    }

//    function extendedKeccak (bytes _data) internal pure returns (bytes32, bytes32) {
//        return (keccak256(abi.encodePacked(uint8(0x00), _data)),
//                keccak256(abi.encodePacked(uint8(0x01), _data)));
//    }

    // TODO: Consider changing to internal
    function extendedKeccakToBN (bytes _data) public pure returns (uint256) {

        bytes32 upper;
        bytes32 lower;

        // Umbral prepends to the data a customization string of 64-bytes.
        // In the case of hash_to_curvebn is 'hash_to_curvebn', padded with zeroes.
        bytes memory input = abi.encodePacked(bytes32("hash_to_curvebn"), bytes32(0x00), _data);

        (upper, lower) = (keccak256(abi.encodePacked(uint8(0x00), input)),
                          keccak256(abi.encodePacked(uint8(0x01), input)));

        uint256 delta = 0x14551231950b75fc4402da1732fc9bec0;
        uint256 n_minus_1 = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364140;

        uint256 upper_half = mulmod(uint256(upper), delta, n_minus_1);
        return 1 + addmod(upper_half, uint256(lower), n_minus_1);
    }

    function verifyState(address _testTarget) public onlyOwner {
        require(address(delegateGet(_testTarget, "escrow()")) == address(escrow));
        require(SignatureVerifier.HashAlgorithm(uint256(delegateGet(_testTarget, "hashAlgorithm()"))) == hashAlgorithm);
        require(uint256(delegateGet(_testTarget, "basePenalty()")) == basePenalty);
        require(uint256(delegateGet(_testTarget, "penaltyHistoryCoefficient()")) == penaltyHistoryCoefficient);
        require(uint256(delegateGet(_testTarget, "percentagePenaltyCoefficient()")) == percentagePenaltyCoefficient);
        require(uint256(delegateGet(_testTarget, "rewardCoefficient()")) == rewardCoefficient);
        require(uint256(delegateGet(_testTarget, "penaltyHistory(address)", bytes32(RESERVED_ADDRESS))) ==
            penaltyHistory[RESERVED_ADDRESS]);
        bytes32 evaluationCFragHash = SignatureVerifier.hash(
            abi.encodePacked(RESERVED_CAPSULE_AND_CFRAG_BYTES), hashAlgorithm);
        require(delegateGet(_testTarget, "evaluatedCFrags(bytes32)", evaluationCFragHash) != bytes32(0));
    }

    function finishUpgrade(address _target) public onlyOwner {
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
