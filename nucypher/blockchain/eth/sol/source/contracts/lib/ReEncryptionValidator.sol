pragma solidity ^0.5.3;

import "contracts/lib/UmbralDeserializer.sol";
import "contracts/lib/Numerology.sol";

/**
* @notice Validates re-encryption correctness.
**/
library ReEncryptionValidator {

    using UmbralDeserializer for bytes;

    // See parameter `u` of `UmbralParameters` class in pyUmbral
    // https://github.com/nucypher/pyUmbral/blob/master/umbral/params.py
    uint8 public constant UMBRAL_PARAMETER_U_SIGN = 0x02;
    uint256 public constant UMBRAL_PARAMETER_U_XCOORD = 0x03c98795773ff1c241fc0b1cced85e80f8366581dda5c9452175ebd41385fa1f;
    uint256 public constant UMBRAL_PARAMETER_U_YCOORD = 0x7880ed56962d7c0ae44d6f14bb53b5fe64b31ea44a41d0316f3a598778f0f936;

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

        // Compute proof's challenge scalar h, used in all ZKP verification equations
        uint256 h = computeProofChallengeScalar(_capsuleBytes, _cFragBytes);

        //////
        // Verifying 1st equation: z*E == h*E_1 + E_2
        //////

        // Input validation: E
        require(Numerology.check_compressed_point(
            _capsule.pointE.sign,
            _capsule.pointE.xCoord,
            _precomputed.pointEyCoord),
            "Precomputed Y coordinate of E doesn't correspond to compressed E point"
        );

        // Input validation: z*E
        require(Numerology.is_on_curve(_precomputed.pointEZxCoord, _precomputed.pointEZyCoord),
                "Point zE is not a valid EC point"
        );
        // TODO: Change validation of EC multiplications to require()
        bool left_hand_element_is_correct = Numerology.ecmulVerify(
            _capsule.pointE.xCoord,     // E_x
            _precomputed.pointEyCoord,  // E_y
            _cFrag.proof.bnSig,         // z
            _precomputed.pointEZxCoord, // zE_x
            _precomputed.pointEZyCoord  // zE_y
        );

        // Input validation: E1
        require(Numerology.check_compressed_point(
            _cFrag.pointE1.sign,          // E1_sign
            _cFrag.pointE1.xCoord,        // E1_x
            _precomputed.pointE1yCoord),  // E1_y
            "Precomputed Y coordinate of E1 doesn't correspond to compressed E1 point"
        );

        // Input validation: h*E1
        require(Numerology.is_on_curve(_precomputed.pointE1HxCoord, _precomputed.pointE1HyCoord),
                "Point h*E1 is not a valid EC point"
        );
        bool rhs_element_is_correct = Numerology.ecmulVerify(
            _cFrag.pointE1.xCoord,          // E1_x
            _precomputed.pointE1yCoord,     // E1_y
            h,
            _precomputed.pointE1HxCoord,    // hE1_x
            _precomputed.pointE1HyCoord     // hE1_y
        );

        // Input validation: E2
        require(Numerology.check_compressed_point(
            _cFrag.proof.pointE2.sign,        // E2_sign
            _cFrag.proof.pointE2.xCoord,      // E2_x
            _precomputed.pointE2yCoord),      // E2_y
            "Precomputed Y coordinate of E2 doesn't correspond to compressed E2 point"
        );

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
        // Verifying 2nd equation: z*V == h*V_1 + V_2
        //////

        // Input validation: V
        require(Numerology.check_compressed_point(
            _capsule.pointV.sign,
            _capsule.pointV.xCoord,
            _precomputed.pointVyCoord),
            "Precomputed Y coordinate of V doesn't correspond to compressed V point"
        );

        // Input validation: z*V
        require(Numerology.is_on_curve(_precomputed.pointVZxCoord, _precomputed.pointVZyCoord),
                "Point zV is not a valid EC point"
        );
        left_hand_element_is_correct = Numerology.ecmulVerify(
            _capsule.pointV.xCoord,     // V_x
            _precomputed.pointVyCoord,  // V_y
            _cFrag.proof.bnSig,         // z
            _precomputed.pointVZxCoord, // zV_x
            _precomputed.pointVZyCoord  // zV_y
        );

        // Input validation: V1
        require(Numerology.check_compressed_point(
            _cFrag.pointV1.sign,         // V1_sign
            _cFrag.pointV1.xCoord,       // V1_x
            _precomputed.pointV1yCoord), // V1_y
            "Precomputed Y coordinate of V1 doesn't correspond to compressed V1 point"
        );

        // Input validation: h*V1
        require(Numerology.is_on_curve(_precomputed.pointV1HxCoord, _precomputed.pointV1HyCoord),
            "Point h*V1 is not a valid EC point"
        );
        rhs_element_is_correct = Numerology.ecmulVerify(
            _cFrag.pointV1.xCoord,          // V1_x
            _precomputed.pointV1yCoord,     // V1_y
            h,
            _precomputed.pointV1HxCoord,    // h*V1_x
            _precomputed.pointV1HyCoord     // h*V1_y
        );

        // Input validation: V2
        require(Numerology.check_compressed_point(
            _cFrag.proof.pointV2.sign,        // V2_sign
            _cFrag.proof.pointV2.xCoord,      // V2_x
            _precomputed.pointV2yCoord),      // V2_y
            "Precomputed Y coordinate of V2 doesn't correspond to compressed V2 point"
        );

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
        // Verifying 3rd equation: z*U == h*U_1 + U_2
        //////

        // We don't have to validate U since it's fixed and hard-coded

        // Input validation: z*U
        require(Numerology.is_on_curve(_precomputed.pointUZxCoord, _precomputed.pointUZyCoord),
                "Point z*U is not a valid EC point"
        );
        left_hand_element_is_correct = Numerology.ecmulVerify(
            UMBRAL_PARAMETER_U_XCOORD,  // U_x
            UMBRAL_PARAMETER_U_YCOORD,  // U_y
            _cFrag.proof.bnSig,         // z
            _precomputed.pointUZxCoord, // zU_x
            _precomputed.pointUZyCoord  // zU_y
        );

        // Input validation: U1  (a.k.a. KFragCommitment)
        require(Numerology.check_compressed_point(
            _cFrag.proof.pointKFragCommitment.sign,     // U1_sign
            _cFrag.proof.pointKFragCommitment.xCoord,   // U1_x
            _precomputed.pointU1yCoord),                // U1_y
            "Precomputed Y coordinate of U1 doesn't correspond to compressed U1 point"
        );

        // Input validation: h*U1
        require(Numerology.is_on_curve(_precomputed.pointU1HxCoord, _precomputed.pointU1HyCoord),
                "Point h*U1 is not a valid EC point"
        );
        rhs_element_is_correct = Numerology.ecmulVerify(
            _cFrag.proof.pointKFragCommitment.xCoord,   // U1_x
            _precomputed.pointU1yCoord,                 // U1_y
            h,
            _precomputed.pointU1HxCoord,    // h*V1_x
            _precomputed.pointU1HyCoord     // h*V1_y
        );

        // Input validation: U2  (a.k.a. KFragPok ("proof of knowledge"))
        require(Numerology.check_compressed_point(
            _cFrag.proof.pointKFragPok.sign,    // U2_sign
            _cFrag.proof.pointKFragPok.xCoord,  // U2_x
            _precomputed.pointU2yCoord),        // U2_y
            "Precomputed Y coordinate of U2 doesn't correspond to compressed U2 point"
        );

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

    // This function was introduced just to facilitate debugging and testing
    // of Alice's address extraction from her signature
    // TODO: Consider moving this somewhere else, or even removing it
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

    // TODO: Consider changing to internal
    // TODO: Unit test wrt to Umbral implementation
    function extendedKeccakToBN (bytes memory _data) public pure returns (uint256) {

        bytes32 upper;
        bytes32 lower;

        // Umbral prepends to the data a customization string of 64-bytes.
        // In the case of hash_to_curvebn is 'hash_to_curvebn', padded with zeroes.
        bytes memory input = abi.encodePacked(bytes32("hash_to_curvebn"), bytes32(0x00), _data);

        (upper, lower) = (keccak256(abi.encodePacked(uint8(0x00), input)),
                          keccak256(abi.encodePacked(uint8(0x01), input)));

        // Let n be the order of secp256k1's group (n = 2^256 - 0x1000003D1)
        // n_minus_1 = n - 1
        // delta = 2^256 mod n_minus_1
        uint256 delta = 0x14551231950b75fc4402da1732fc9bec0;
        uint256 n_minus_1 = 0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364140;

        uint256 upper_half = mulmod(uint256(upper), delta, n_minus_1);
        return 1 + addmod(upper_half, uint256(lower), n_minus_1);
    }
}
