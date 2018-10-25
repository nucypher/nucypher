pragma solidity ^0.4.25;


import "./lib/SignatureVerifier.sol";


library SerializationLibrary {

    //bytes == 33 bytes
    struct OriginalCapsule {
//        bytes paramsU;
        bytes pointE;
        bytes pointV;
        bytes32 bnSig;
    }

    struct CorrectnessProof {
        bytes pointE2;
        bytes pointV2;
        bytes pointKFragCommitment;
        bytes pointKFragPok;
        bytes32 bnSig;
        bytes kFragSignature; // 66 bytes
        bytes metadata; // any length
    }

    struct CapsuleFrag {
        bytes pointE1;
        bytes pointV1;
        bytes32 kFragId;
        bytes pointNonInteractive;
        bytes pointXCoord;
        CorrectnessProof proof;
    }

    uint8 constant BIG_NUM_SIZE = 32;
    uint8 constant POINT_SIZE = 33;
    uint8 constant SIGNATURE_SIZE = 64;
    uint8 constant ORIGINAL_CAPSULE_SIZE = 2 * POINT_SIZE + BIG_NUM_SIZE;
    uint8 constant CORRECTNESS_PROOF_SIZE = 4 * POINT_SIZE + BIG_NUM_SIZE + SIGNATURE_SIZE;
    uint8 constant CAPSULE_FRAG_SIZE = 4 * POINT_SIZE + BIG_NUM_SIZE;
    uint8 constant FULL_CAPSULE_FRAG_SIZE = CAPSULE_FRAG_SIZE + CORRECTNESS_PROOF_SIZE;

    function toOriginalCapsule(bytes memory _capsuleBytes)
        internal pure returns (OriginalCapsule memory capsule)
    {
        require(_capsuleBytes.length == ORIGINAL_CAPSULE_SIZE);
        capsule.pointE = new bytes(POINT_SIZE);
        capsule.pointV = new bytes(POINT_SIZE);

        uint256 pointer = getPointer(_capsuleBytes);
        pointer = copyPointBytes(pointer, capsule.pointE);
        pointer = copyPointBytes(pointer, capsule.pointV);
        capsule.bnSig = getBytes32(pointer);
    }

    function toCorrectnessProof(uint256 _pointer, uint256 _proofBytesLength)
        internal pure returns (CorrectnessProof memory proof)
    {
        require(_proofBytesLength >= CORRECTNESS_PROOF_SIZE);

        proof.pointE2 = new bytes(POINT_SIZE);
        proof.pointV2 = new bytes(POINT_SIZE);
        proof.pointKFragCommitment = new bytes(POINT_SIZE);
        proof.pointKFragPok = new bytes(POINT_SIZE);
        proof.kFragSignature = new bytes(SIGNATURE_SIZE);

        _pointer = copyPointBytes(_pointer, proof.pointE2);
        _pointer = copyPointBytes(_pointer, proof.pointV2);
        _pointer = copyPointBytes(_pointer, proof.pointKFragCommitment);
        _pointer = copyPointBytes(_pointer, proof.pointKFragPok);
        proof.bnSig = getBytes32(_pointer);
        _pointer += BIG_NUM_SIZE;
        // TODO optimize
        _pointer = copyBytes(_pointer, proof.kFragSignature, SIGNATURE_SIZE);
        if (_proofBytesLength > CORRECTNESS_PROOF_SIZE) {
            proof.metadata = new bytes(_proofBytesLength - CORRECTNESS_PROOF_SIZE);
            copyBytes(_pointer, proof.metadata, proof.metadata.length);
        }
    }

    function toCorrectnessProof(bytes memory _proofBytes)
        internal pure returns (CorrectnessProof memory proof)
    {
        uint256 pointer = getPointer(_proofBytes);
        return toCorrectnessProof(pointer, _proofBytes.length);
    }

    function toCapsuleFrag(bytes memory _cFragBytes)
        internal pure returns (CapsuleFrag memory cFrag)
    {
        uint256 cFragBytesLength = _cFragBytes.length;
        require(cFragBytesLength >= FULL_CAPSULE_FRAG_SIZE);

        cFrag.pointE1 = new bytes(POINT_SIZE);
        cFrag.pointV1 = new bytes(POINT_SIZE);
        cFrag.pointNonInteractive = new bytes(POINT_SIZE);
        cFrag.pointXCoord = new bytes(POINT_SIZE);

        uint256 pointer = getPointer(_cFragBytes);
        pointer = copyPointBytes(pointer, cFrag.pointE1);
        pointer = copyPointBytes(pointer, cFrag.pointV1);
        cFrag.kFragId = getBytes32(pointer);
        pointer += BIG_NUM_SIZE;
        pointer = copyPointBytes(pointer, cFrag.pointNonInteractive);
        pointer = copyPointBytes(pointer, cFrag.pointXCoord);

        cFrag.proof = toCorrectnessProof(pointer, cFragBytesLength - CAPSULE_FRAG_SIZE);
    }

    function getPointer(bytes memory _bytes) internal pure returns (uint256 pointer) {
        assembly {
            pointer := add(_bytes, 32) // skip array length
        }
    }

    function getBytes32(uint _bytesPointer) internal pure returns (bytes32 result) {
        assembly {
            result := mload(_bytesPointer)
        }
    }

    // Assumes that enough memory has been allocated to store in target.
    function copyPointBytes(uint _bytesPointer, bytes memory _target)
        internal
        pure
        returns (uint256 resultPointer)
    {
        assembly {
            let destination := add(_target, 32) // skip array length value
            mstore(destination, mload(_bytesPointer))
            resultPointer := add(_bytesPointer, 1)
            mstore8(add(destination, 32), mload(resultPointer)) // read one last byte
            resultPointer := add(resultPointer, 32)
        }
    }

    // Assumes that enough memory has been allocated to store in target.
    function copyBytes(uint _bytesPointer, bytes memory _target, uint _bytesLength)
        internal
        pure
        returns (uint256 resultPointer)
    {
        // Exploiting the fact that 'target' was the last thing to be allocated,
        // we can write entire words, and just overwrite any excess.
        assembly {
            // evm operations on words
            let words := div(add(_bytesLength, 31), 32)
            let source := _bytesPointer
            let destination := add(_target, 32)
            for
                { let i := 0 } // start at arr + 0x20 -> first byte corresponds to length
                lt(i, words)
                { i := add(i, 1) }
            {
                let offset := mul(i, 32)
                mstore(add(destination, offset), mload(add(source, offset)))
            }
            mstore(add(_target, add(32, mload(_target))), 0)
        }
        resultPointer = _bytesPointer + _bytesLength;
    }

}


contract SerializationLibraryMock {

    function toOriginalCapsule(bytes memory _capsuleBytes)
        public pure returns (bytes memory pointE, bytes memory pointV, bytes32 bnSig)
    {
        SerializationLibrary.OriginalCapsule memory capsule =
            SerializationLibrary.toOriginalCapsule(_capsuleBytes);
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
        SerializationLibrary.CorrectnessProof memory proof =
            SerializationLibrary.toCorrectnessProof(_proofBytes);
        pointE2 = proof.pointE2;
        pointV2 = proof.pointV2;
        pointKFragCommitment = proof.pointKFragCommitment;
        pointKFragPok = proof.pointKFragPok;
        bnSig = proof.bnSig;
        kFragSignature = proof.kFragSignature;
        metadata = proof.metadata;
    }

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
        SerializationLibrary.CapsuleFrag memory cFrag =
            SerializationLibrary.toCapsuleFrag(_cFragBytes);
        SerializationLibrary.CorrectnessProof memory proof = cFrag.proof;
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
        SerializationLibrary.CapsuleFrag memory cFrag =
            SerializationLibrary.toCapsuleFrag(_cFragBytes);
        pointE1 = cFrag.pointE1;
        pointV1 = cFrag.pointV1;
        kFragId = cFrag.kFragId;
        pointNonInteractive = cFrag.pointNonInteractive;
        pointXCoord = cFrag.pointXCoord;
    }
}


/**
* @notice Challenges for NuCypher net characters
* @dev TODO move or integrate with MinersEscrow
**/
contract ChallengeAgent {

    uint256 constant PENALTY = 100; // TODO

    MinersEscrowStub public escrow;
    SignatureVerifier.HashAlgorithm public hashAlgorithm;
    mapping (bytes32 => bool) public challengedCFrags;

    /**
    * @param _escrow Escrow contract
    * @param _hashAlgorithm Hashing algorithm
    **/
    constructor(
        MinersEscrowStub _escrow,
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


// TODO move to tests
contract MinersEscrowStub {

    mapping (address => uint256) public minerInfo;

    function setMinerInfo(address _miner, uint256 _amount) public {
        minerInfo[_miner] = _amount;
    }

    function getLockedTokens(address _miner)
        public view returns (uint256)
    {
        return minerInfo[_miner];
    }

    function slashMiner(address _miner, uint256 _amount) public {
        minerInfo[_miner] -= _amount;
    }

}

