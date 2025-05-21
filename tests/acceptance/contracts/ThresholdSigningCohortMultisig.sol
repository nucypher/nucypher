// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/interfaces/IERC1271.sol";
import "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import "@openzeppelin/contracts/utils/cryptography/MessageHashUtils.sol";
import "@openzeppelin-upgradeable/contracts/proxy/utils/Initializable.sol";
import "@openzeppelin-upgradeable/contracts/access/OwnableUpgradeable.sol";

contract ThresholdSigningCohortMultisig is
    Initializable,
    IERC1271,
    OwnableUpgradeable
{
    using ECDSA for bytes32;

    // events
    event Executed(
        address indexed sender,
        uint256 indexed nonce,
        address indexed destination,
        uint256 value
    );
    event SignerAdded(address indexed signer);
    event SignerRemoved(address indexed signer);
    event SignerReplaced(address indexed signer, address newSigner);
    event SignedMessageCached(bytes32 indexed hash);
    event ThresholdUpdated(uint16 threshold);

    uint256 public constant MAX_SIGNER_COUNT = 40;

    uint256 public nonce;
    mapping(address => bool) public isSigner;
    address[] public signers;
    uint16 public threshold;

    bytes4 internal constant MAGICVALUE = 0x1626ba7e;
    bytes4 internal constant INVALID_SIGNATURE = 0xffffffff;
    mapping(bytes32 => bytes32) public validSignatures;

    // Random Number Generation
    struct RandomNumberRequest {
        address requester;
        bool fulfilled;
        uint256 randomValue;
        bytes[] randomnessValues;
        bytes[] proofs;
    }
    mapping(bytes32 => RandomNumberRequest) public randomRequests;
    uint256 private randomNonce;
    mapping(bytes32 => mapping(address => bool)) public randomRequestSigners;

    event RandomNumberRequested(bytes32 indexed requestHash, address requester);
    event RandomnessSubmitted(bytes32 indexed requestHash, address signer, bytes randomness, bytes proof);
    event RandomNumberGenerated(bytes32 indexed requestHash, uint256 randomValue);

    // JWT-like Token Issuance
    struct TokenIssuanceRequest {
        address requester;
        bool fulfilled;
        string tokenPayload;
        bytes[] collectedSignatures;
        bytes thresholdSignature;
    }
    mapping(bytes32 => TokenIssuanceRequest) public tokenRequests;
    mapping(bytes32 => mapping(address => bool)) public tokenRequestSigners;

    event TokenIssuanceRequested(bytes32 indexed requestHash, address requster, string tokenPayload);
    event TokenIssuanceApproved(bytes32 indexed requestHash, string tokenPayload, bytes aggregatedSignature);

    /**
     * @param _signers List of signers.
     * @param _threshold Threshold number of required signings
     * @param _initialOwner Initial owner of the contract
     **/
    function initialize(
        address[] memory _signers,
        uint16 _threshold,
        address _initialOwner
    ) public initializer {
        require(owner() == address(0), "Already initialized");
        __Ownable_init(_initialOwner);
        require(
            _signers.length <= MAX_SIGNER_COUNT && _threshold <= _signers.length && _threshold > 0,
            "Invalid arguments"
        );

        for (uint256 i = 0; i < _signers.length; i++) {
            address signer = _signers[i];
            require(!isSigner[signer] && signer != address(0), "Already a signer");
            isSigner[signer] = true;
        }
        nonce = 1;
        signers = _signers;
        threshold = _threshold;
    }

    /**
     * @notice Get unsigned hash for transaction parameters
     * @dev Follows ERC191 signature scheme: https://github.com/ethereum/EIPs/issues/191
     * @param sender Trustee who will execute the transaction
     * @param destination Destination address
     * @param value Amount of ETH to transfer
     * @param data Call data
     * @param nonce Nonce
     **/
    function getUnsignedTransactionHash(
        address sender,
        address destination,
        uint256 value,
        bytes memory data,
        uint256 nonce
    ) public view returns (bytes32) {
        bytes memory encodedData = abi.encodePacked(
            address(this),
            sender,
            destination,
            value,
            data,
            nonce
        );
        return MessageHashUtils.toEthSignedMessageHash(encodedData);
    }

    /**
     * @dev Note that address recovered from signatures must be strictly increasing
     * @param destination Destination address
     * @param value Amount of ETH to transfer
     * @param data Call data
     * @param signature The aggregated signatures for signers
     **/
    function execute(
        address destination,
        uint256 value,
        bytes memory data,
        bytes memory signature
    ) external {
        bytes32 _hash = getUnsignedTransactionHash(msg.sender, destination, value, data, nonce);
        require(isValidSignature(_hash, signature) == MAGICVALUE, "Invalid Signature");
        emit Executed(msg.sender, nonce, destination, value);
        nonce++;
        (bool success, ) = destination.call{value: value}(data);
        require(success, "Transaction failed");
    }

    /**
     * @notice Check if the signatures are valid.
     * @param hash Hash of the transaction
     * @param signature The signatures for signers
     **/
    function isValidSignature(
        bytes32 hash,
        bytes memory signature
    ) public view override returns (bytes4) {
        // split up signature bytes into array
        require(signature.length >= (threshold * 65), "Invalid threshold of signatures");
        if (validSignatures[hash] == keccak256(signature)) {
            // TODO is this sufficient?
            // - in this case the message hash was previously signed and cached
            return MAGICVALUE;
        }

        address lastSigner = address(0);
        for (uint16 i = 0; i < threshold; i++) {
            (uint8 v, bytes32 r, bytes32 s) = signatureSplit(signature, i);
            address recovered = ecrecover(hash, v, r, s);
            if (!isSigner[recovered]) {
                return INVALID_SIGNATURE;
            }
            // ensure signatures are for different signers
            if (recovered <= lastSigner) {
                return INVALID_SIGNATURE;
            }
            lastSigner = recovered;
        }

        return MAGICVALUE;
    }

    /**
     * @notice Splits signature bytes into `uint8 v, bytes32 r, bytes32 s`.
     * @dev Make sure to perform a bounds check for @param pos, to avoid out of bounds access on @param signatures
     *      The signature format is a compact form of {bytes32 r}{bytes32 s}{uint8 v}
     *      Compact means uint8 is not padded to 32 bytes.
     * @param _signatures Concatenated {r, s, v} signatures.
     * @param _pos Which signature to read.
     *            A prior bounds check of this parameter should be performed, to avoid out of bounds access.
     * @return v Recovery ID or Safe signature type.
     * @return r Output value r of the signature.
     * @return s Output value s of the signature.
     */
    function signatureSplit(
        bytes memory _signatures,
        uint256 _pos
    ) internal pure returns (uint8 v, bytes32 r, bytes32 s) {
        /* solhint-disable no-inline-assembly */
        /// @solidity memory-safe-assembly
        assembly {
            let signaturePos := mul(0x41, _pos)
            r := mload(add(_signatures, add(signaturePos, 0x20)))
            s := mload(add(_signatures, add(signaturePos, 0x40)))
            v := byte(0, mload(add(_signatures, add(signaturePos, 0x60))))
        }
        /* solhint-enable no-inline-assembly */
    }

    /**
     * @notice Allows to add a new signer
     * @dev Transaction has to be sent by `execute` method.
     * @param newSigner Address of new signer
     **/
    function addSigner(address newSigner) public onlyOwner {
        require(signers.length < MAX_SIGNER_COUNT, "At max signers");
        require(newSigner != address(0) && !isSigner[newSigner], "Invalid signer");
        signers.push(newSigner);
        isSigner[newSigner] = true;
        emit SignerAdded(newSigner);
    }

    /**
     * @notice Allows to remove an signer
     * @dev Transaction has to be sent by `execute` method.
     * @param signerToRemove Address of signer
     **/
    function removeSigner(address signerToRemove) public onlyOwner {
        require(signers.length > threshold && isSigner[signerToRemove], "Invalid signer");
        isSigner[signerToRemove] = false;

        uint256 index = signers.length;
        for (uint256 i = 0; i < signers.length; i++) {
            if (signers[i] == signerToRemove) {
                index = i;
                break;
            }
        }
        require(index < signers.length && signers[index] == signerToRemove, "Signer not found");
        signers[index] = signers[signers.length - 1];
        signers.pop(); // Remove last element
        emit SignerRemoved(signerToRemove);
    }

    /**
     * @notice Allows to replace an signer with a new signer.
     * @dev Transaction has to be sent by `execute` method.
     * @param oldSigner Address of signer to be replaced.
     * @param newSigner Address of new signer.
     */
    function replaceSigner(address oldSigner, address newSigner) public onlyOwner {
        require(isSigner[oldSigner] && !isSigner[newSigner], "Invalid Signer");

        removeSigner(oldSigner);
        addSigner(newSigner);
        emit SignerReplaced(oldSigner, newSigner);
    }

    function getSigners() public view returns (address[] memory) {
        return signers;
    }

    /**
     * @notice Allows to change the threshold number of signatures
     * @dev Transaction has to be sent by `execute` method
     * @param newThreshold Threshold number of required signatures
     **/
    function changeThreshold(uint16 newThreshold) public onlyOwner {
        require(newThreshold <= signers.length && newThreshold > 0, "Invalid threshold");
        threshold = newThreshold;
        emit ThresholdUpdated(newThreshold);
    }

    /**
     * @notice Bulk update of multisig
     * @param newSigners List of signers.
     * @param newThreshold Threshold number of required signatures (0 = no change)
     * @param clearSigners Whether to clear existing signers or not
     **/
    function updateMultiSigParameters(
        address[] calldata newSigners,
        uint16 newThreshold,
        bool clearSigners
    ) external onlyOwner {
        uint256 signersLength_ = newSigners.length;
        uint256 storedSignersLength_ = signers.length;

        uint256 signersCount_ = clearSigners
            ? signersLength_
            : signersLength_ + storedSignersLength_;
        require(newThreshold <= signersCount_, "Invalid threshold");
        require(signersCount_ <= MAX_SIGNER_COUNT, "Too Many Signers");

        if (clearSigners) {
            removeAllSigners();
        }

        for (uint256 i = 0; i < signersLength_; ++i) {
            address newSigner_ = newSigners[i];
            require(newSigner_ != address(0), "Invalid signer");
            addSigner(newSigner_);
        }

        if (newThreshold != 0) {
            changeThreshold(newThreshold);
        }
    }

    function removeAllSigners() internal {
        for (uint256 i = 0; i < signers.length; ++i) {
            address oldSigner = signers[i];
            delete isSigner[oldSigner];
            emit SignerRemoved(oldSigner);
        }
        delete signers;
    }

    //
    // Cached signatures (in case of cohort rotation/handover)
    //

    function saveSignature(bytes32 hash, bytes memory signature) public {
        // Save signature
        require(isValidSignature(hash, signature) == MAGICVALUE, "Invalid Signature");

        // TODO: is this sufficient?
        validSignatures[hash] = keccak256(signature);
        emit SignedMessageCached(hash);
    }

    function deposit() external payable {}

    //
    // Random Number Generation
    //

    function requestRandomNumber() external {
        randomNonce++;
        bytes32 requestHash = keccak256(abi.encodePacked(msg.sender, block.timestamp, randomNonce));
        require(randomRequests[requestHash].requester == address(0), "Random Number request already exists");

        RandomNumberRequest storage request = randomRequests[requestHash];
        request.requester = msg.sender;
        request.fulfilled = false;
        request.randomValue = 0;

        emit RandomNumberRequested(requestHash, msg.sender);
    }

    function submitRandomness(bytes32 requestHash, bytes memory randomness, bytes memory proof) external {
        require(isSigner[msg.sender], "Not an authorized signer");
        require(!randomRequestSigners[requestHash][msg.sender], "Submission already made");

        RandomNumberRequest storage request = randomRequests[requestHash];
        require(request.requester != address(0), "Invalid request");
        require(!request.fulfilled, "Random Number request already fulfilled");

        request.randomnessValues.push(randomness);
        request.proofs.push(proof);
        randomRequestSigners[requestHash][msg.sender] = true;
        if (request.randomnessValues.length >= threshold) {
            finalizeRandomness(requestHash);
        }

        emit RandomnessSubmitted(requestHash, msg.sender, randomness, proof);
    }

    function getRandomNumber(bytes32 requestHash) external view returns (uint256) {
        require(randomRequests[requestHash].fulfilled, "Random number not generated");
        return randomRequests[requestHash].randomValue;
    }

    function finalizeRandomness(bytes32 requestHash) internal {
        RandomNumberRequest storage request = randomRequests[requestHash];
        require(request.randomnessValues.length >= threshold, "Not enough submissions");
        require(request.randomValue == 0, "Random number already generated");

        bytes32 finalRandomness;
        for (uint256 i = 0; i < request.randomnessValues.length; i++) {
            finalRandomness = keccak256(abi.encodePacked(finalRandomness, request.randomnessValues[i]));
        }
        uint256 finalRandomValue =  uint256(finalRandomness) % 10**18; // Random number within range
        request.fulfilled = true;
        request.randomValue = finalRandomValue;

        emit RandomNumberGenerated(requestHash, finalRandomValue);
    }


    //
    // JWT-like token issuance
    //
    function requestTokenIssuance(string memory tokenPayload) external {
        require(msg.sender == owner(), "Only owner can request token");
        bytes32 requestHash = keccak256(abi.encodePacked(tokenPayload));
        require(tokenRequests[requestHash].requester == address(0), "Request already exists");

        TokenIssuanceRequest storage request = tokenRequests[requestHash];
        request.requester = msg.sender;
        request.fulfilled = false;
        request.tokenPayload = tokenPayload;

        emit TokenIssuanceRequested(requestHash, msg.sender, tokenPayload);
    }

    function approveTokenIssuance(bytes32 requestHash, bytes memory signature) external {
        require(isSigner[msg.sender], "Not an authorized signer");
        require(tokenRequests[requestHash].requester != address(0), "Invalid token request");

        TokenIssuanceRequest storage request = tokenRequests[requestHash];

        require(!request.fulfilled, "Token request already fulfilled");

        address recovered = ECDSA.recover(requestHash, signature);
        require(isSigner[recovered], "Invalid signer");
        require(!tokenRequestSigners[requestHash][recovered], "Signature already submitted");

        tokenRequestSigners[requestHash][recovered] = true;
        request.collectedSignatures.push(signature);
        if (request.collectedSignatures.length >= threshold) {
            finalizeTokenApproval(requestHash);
        }
    }

    function finalizeTokenApproval(bytes32 requestHash) internal {
        TokenIssuanceRequest storage request = tokenRequests[requestHash];
        require(request.collectedSignatures.length >= threshold, "Not enough signatures");

        bytes memory aggregatedSignature;
        for (uint256 i = 0; i < threshold; i++) {
            aggregatedSignature = abi.encodePacked(aggregatedSignature, request.collectedSignatures[i]);
        }
        request.thresholdSignature = aggregatedSignature;
        request.fulfilled = true;

        emit TokenIssuanceApproved(requestHash, tokenRequests[requestHash].tokenPayload, aggregatedSignature);
    }

    function verifyOnChainTokenSignature(string memory tokenPayload, bytes memory signature) external view returns (bool) {
        bytes32 requestHash = keccak256(abi.encodePacked(tokenPayload));
        return keccak256(signature) == keccak256(tokenRequests[requestHash].thresholdSignature);
    }

        function getTokenPayloadHash(string memory tokenPayload) external pure returns (bytes32) {
        return keccak256(abi.encodePacked(tokenPayload));
    }

}
