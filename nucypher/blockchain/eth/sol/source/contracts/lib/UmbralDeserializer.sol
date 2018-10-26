pragma solidity ^0.4.25;


/**
* @notice Deserialization library for Umbral objects
**/
library UmbralDeserializer {

    //bytes == 33 bytes
    struct OriginalCapsule {
        byte pointESign;
        bytes32 pointEXCoord;
        bytes pointE;
        bytes pointV;
        uint256 bnSig;
    }

    struct CorrectnessProof {
        bytes pointE2;
        bytes pointV2;
        bytes pointKFragCommitment;
        bytes pointKFragPok;
        uint256 bnSig;
        bytes kFragSignature; // 64 bytes
        bytes metadata; // any length
    }

    struct CapsuleFrag {
        bytes pointE1;
        bytes pointV1;
        bytes32 kFragId;
        bytes pointPrecursor;
        CorrectnessProof proof;
    }

    // TODO rename
    struct PreCalculatedData {
        bytes data;
    }

    uint8 constant BIG_NUM_SIZE = 32;
    uint8 constant POINT_SIZE = 33;
    uint8 constant SIGNATURE_SIZE = 64;
    uint8 constant ORIGINAL_CAPSULE_SIZE = 2 * POINT_SIZE + BIG_NUM_SIZE;
    uint8 constant CORRECTNESS_PROOF_SIZE = 4 * POINT_SIZE + BIG_NUM_SIZE + SIGNATURE_SIZE;
    uint8 constant CAPSULE_FRAG_SIZE = 4 * POINT_SIZE + BIG_NUM_SIZE;
    uint8 constant FULL_CAPSULE_FRAG_SIZE = CAPSULE_FRAG_SIZE + CORRECTNESS_PROOF_SIZE;

    /**
    * @notice Deserialize to original capsule (not activated)
    **/
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

    /**
    * @notice Deserialize to correctness proof
    * @param _pointer Proof bytes memory pointer
    * @param _proofBytesLength Proof bytes length
    **/
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

    /**
    * @notice Deserialize to correctness proof
    **/
    function toCorrectnessProof(bytes memory _proofBytes)
        internal pure returns (CorrectnessProof memory proof)
    {
        uint256 pointer = getPointer(_proofBytes);
        return toCorrectnessProof(pointer, _proofBytes.length);
    }

    /**
    * @notice Deserialize to capsule frag
    **/
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

    /**
    * @notice Deserialize to pre calculated data
    **/
    // TODO rename
    function toPreCalculatedData(bytes memory _preCalculatedData)
        internal pure returns (PreCalculatedData memory data)
    {
        data.data = _preCalculatedData;
    }

    // TODO extract to external library if needed
    /**
    * @notice Get the memory pointer for start of array
    **/
    function getPointer(bytes memory _bytes) internal pure returns (uint256 pointer) {
        assembly {
            pointer := add(_bytes, 32) // skip array length
        }
    }

    /**
    * @notice Read 32 bytes from memory in pointer position
    **/
    function getBytes32(uint256 _pointer) internal pure returns (bytes32 result) {
        assembly {
            result := mload(_pointer)
        }
    }

    /**
    * @notice Copy 33 bytes (point size) from the source pointer to the target array
    * @dev Assumes that enough memory has been allocated to store in target
    * @param _bytesPointer Source memory pointer
    * @param _target Target array
    **/
    function copyPointBytes(uint256 _bytesPointer, bytes memory _target)
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

    /**
    * @notice Copy bytes from the source pointer to the target array
    * @dev Assumes that enough memory has been allocated to store in target.
    * Also assumes that '_target' was the last thing that was allocated
    * @param _bytesPointer Source memory pointer
    * @param _target Target array
    * @param _bytesLength Number of bytes to copy
    **/
    function copyBytes(uint256 _bytesPointer, bytes memory _target, uint256 _bytesLength)
        internal
        pure
        returns (uint256 resultPointer)
    {
        // Exploiting the fact that '_target' was the last thing to be allocated,
        // we can write entire words, and just overwrite any excess.
        assembly {
            // evm operations on words
            let words := div(add(_bytesLength, 31), 32)
            let source := _bytesPointer
            let destination := add(_target, 32)
            for
                { let i := 0 } // start at arr + 32 -> first byte corresponds to length
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
