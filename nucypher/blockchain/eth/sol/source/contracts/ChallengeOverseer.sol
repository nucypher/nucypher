pragma solidity ^0.4.25;


import "./lib/UmbralDeserializer.sol";
import "./lib/SignatureVerifier.sol";
import "./lib/Numerology.sol";
import "./MinersEscrow.sol";


/**
* @notice Challenges for NuCypher net characters
**/
contract ChallengeOverseer {

    uint8 public constant UMBRAL_PARAMETER_U_SIGN = 0x02;
    uint256 public constant UMBRAL_PARAMETER_U_XCOORD = 0x03c98795773ff1c241fc0b1cced85e80f8366581dda5c9452175ebd41385fa1f;

    using UmbralDeserializer for bytes;

    // TODO events
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
    )
        public
    {
        require(address(_escrow) != 0x0);
        escrow = _escrow;
        hashAlgorithm = _hashAlgorithm;
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
    function challengeCFrag(
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

        // Check that CFrag is not challenged yet
        bytes32 challengeHash = SignatureVerifier.hash(
            abi.encodePacked(_capsuleBytes, _cFragBytes), hashAlgorithm);
        require(!challengedCFrags[challengeHash]);

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
        UmbralDeserializer.Capsule memory capsule = _capsuleBytes.toCapsule();
        UmbralDeserializer.CapsuleFrag memory cFrag = _cFragBytes.toCapsuleFrag();
        UmbralDeserializer.PreComputedData memory data = _preComputedData.toPreComputedData();
        challengedCFrags[challengeHash] = true;
        if (!isCapsuleFragCorrect(capsule, cFrag, data)) {
            // TODO calculate penalty - depends on how many time was slashed
            // TODO set reward
            escrow.slashMiner(miner, PENALTY, msg.sender, PENALTY);
        }
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

    /**
    * @notice Check correctness of re-encryption
    * @param _capsule Capsule
    * @param _cFrag Capsule frag
    * @param _precomputed Additional precomputed data
    **/
    function isCapsuleFragCorrect(
        UmbralDeserializer.Capsule memory _capsule,
        UmbralDeserializer.CapsuleFrag memory _cFrag,
        UmbralDeserializer.PreComputedData memory _precomputed
    )
        // TODO make public when possible
        internal pure returns (bool)
    {

        // Compute h = hash_to_bignum(e, e1, e2, v, v1, v2, u, u1, u2)
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
            _cFrag.proof.pointKFragPok.xCoord
        );

        uint256 h = extendedKeccakToBN(hashInput);

        //////
        // Verifying equation: z*E + h*E_1 = E_2
        //////

        // Input validation: E
        require(Numerology.check_compressed_point(
            _capsule.pointE.sign,
            _capsule.pointE.xCoord,
            _precomputed.pointEyCoord
        ));

        bool ez_is_correct = Numerology.ecmulVerify(
            _capsule.pointE.xCoord,     // E_x
            _precomputed.pointEyCoord,  // E_y
            _cFrag.proof.bnSig,         // z
            _precomputed.pointEZxCoord, // zE_x
            _precomputed.pointEZyCoord  // zE_y
        );

        require(Numerology.check_compressed_point(
            _cFrag.pointE1.sign,         // E_sign
            _cFrag.pointE1.xCoord,      // E1_x
            _precomputed.pointE1yCoord  // E1_y
        ));

        bool e1h_is_correct = Numerology.ecmulVerify(
            _cFrag.pointE1.xCoord,          // E1_x
            _precomputed.pointE1yCoord,     // E1_y
            h,
            _precomputed.pointE1HxCoord,    // hE1_x
            _precomputed.pointE1HyCoord     // hE1_y
        );

        require(Numerology.check_compressed_point(
            _cFrag.proof.pointE2.sign,        // E2_sign
            _cFrag.proof.pointE2.xCoord,      // E2_x
            _precomputed.pointE2yCoord        // E2_y
        ));

        bool sum_is_correct = Numerology.eqAffineJacobian(
            [_cFrag.proof.pointE2.xCoord, _precomputed.pointE2yCoord],
            Numerology.addAffineJacobian(
                [_precomputed.pointEZxCoord,  _precomputed.pointEZyCoord],
                [_precomputed.pointE1HxCoord, _precomputed.pointE1HyCoord]
            )
        );

        // TODO: Repeat with v and u
        return ez_is_correct && e1h_is_correct && sum_is_correct;
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
}
