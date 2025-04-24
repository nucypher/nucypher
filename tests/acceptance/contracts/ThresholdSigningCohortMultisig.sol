// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "@nucypher-contracts/contracts/coordination/ThresholdSigningMultisig.sol";

contract ThresholdSigningCohortMultisig is ThresholdSigningMultisig {
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
