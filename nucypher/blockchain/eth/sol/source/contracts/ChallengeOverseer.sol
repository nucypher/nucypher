pragma solidity ^0.4.25;


import "./lib/UmbralDeserializer.sol";
import "./lib/SignatureVerifier.sol";
import "./MinersEscrow.sol";


/**
* @notice Challenges for NuCypher net characters
* @dev TODO move or integrate with MinersEscrow
**/
contract ChallengeOverseer {
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
    ) public {
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
        // TODO rename
        bytes _preComputedData
    ) public {
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
        require(escrow.getLockedTokens(miner) > 0); // TODO check that miner can be slashed

        // Verify correctness of re-encryption
        UmbralDeserializer.Capsule memory capsule = _capsuleBytes.toCapsule();
        UmbralDeserializer.CapsuleFrag memory cFrag = _cFragBytes.toCapsuleFrag();
        // TODO rename
        UmbralDeserializer.PreComputedData memory data = _preComputedData.toPreComputedData();
        if (!isCapsuleFragCorrect(capsule, cFrag, data)) {
            escrow.slashMiner(miner, PENALTY);
        }
        challengedCFrags[challengeHash] = true;
    }

    /**
    * @notice Prepare public key before verification (cut the first byte)
    **/
    function preparePublicKey(bytes memory _preparedPublicKey, bytes memory _publicKey) public pure {
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
    * @param _data Additional data
    **/
    function isCapsuleFragCorrect(
        UmbralDeserializer.Capsule memory _capsule,
        UmbralDeserializer.CapsuleFrag memory _cFrag,
        UmbralDeserializer.PreComputedData memory _data
    // TODO make public when possible
    ) internal pure returns (bool) {
        // TODO use Numerology repo
//        return _capsule.pointE.length == 33 &&
//            _cFrag.proof.metadata.length == 33 &&
//            _data.data.length == 22; // just for tests
    }

}
