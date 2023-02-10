// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

import "./proxy/Upgradeable.sol";

/**
* @title CoordinatorV3
* @notice Coordination layer for DKG-TDec
*/
contract CoordinatorV3 is Upgradeable {

    // Ritual
    event StartRitual(uint32 indexed ritualId, address[] nodes, address initiator);
    event StartTranscriptRound(uint32 indexed ritualId);
    event StartAggregationRound(uint32 indexed ritualId);
    event EndRitual(uint32 indexed ritualId, RitualStatus status, address initiator);

    // Node
    event TranscriptPosted(uint32 indexed ritualId, address indexed node, bytes32 transcriptDigest);
    event AggregationPosted(uint32 indexed ritualId, address indexed node, bytes32 aggregatedTranscriptDigest);

    // Admin
    event TimeoutChanged(uint32 oldTimeout, uint32 newTimeout);
    event MaxDkgSizeChanged(uint32 oldSize, uint32 newSize);

    enum RitualStatus {
        WAITING_FOR_TRANSCRIPTS,
        WAITING_FOR_AGGREGATIONS,
        WAITING_FOR_FINALIZATION,
        FAILED_TIMEOUT,
        FAILED_INVALID_TRANSCRIPTS,
        FINALIZED
    }

    struct Rite {
        address node;
        bool aggregated;
        bytes transcript;
    }

    struct Ritual {
        uint32 id;
        address initiator;
        uint32 dkgSize;
        uint32 initTimestamp;
        uint32 totalTranscripts;
        uint32 totalAggregations;
        uint32 threshold;
        bytes32 publicMaterial;
        RitualStatus status;
        Rite[] rite;
    }

    Ritual[] public rituals;

    uint32 public timeout;
    uint32 public maxDkgSize;

    constructor(uint32 _timeout) {
        timeout = _timeout;
        maxDkgSize = 64;  // TODO Who knows? https://www.youtube.com/watch?v=hzqFmXZ8tOE&ab_channel=Protoje
    }

    function _checkActiveRitual(Ritual storage _ritual) internal {
        uint32 delta = uint32(block.timestamp) - _ritual.initTimestamp;
        if (delta > timeout) {
            _ritual.status = RitualStatus.FAILED_TIMEOUT;
            emit EndRitual(_ritual.id, _ritual.status); // penalty hook, missing nodes can be known at this stage
            revert("Ritual timed out");
        }
    }

    function setTimeout(uint32 newTimeout) external onlyOwner {
        uint32 oldTimeout = timeout;
        timeout = newTimeout;
        emit TimeoutChanged(oldTimeout, newTimeout);
    }

    function setMaxDkgSize(uint32 newSize) external onlyOwner {
        uint32 oldSize = maxDkgSize;
        maxDkgSize = newSize;
        emit MaxDkgSizeChanged(oldSize, newSize);
    }

    function numberOfRituals() external view returns(uint256) {
        return rituals.length;
    }

    function getRites(uint32 ritualId) external view returns(Rite[] memory) {
        Rite[] memory rites = new Rite[](rituals[ritualId].rite.length);
        for(uint32 i=0; i < rituals[ritualId].rite.length; i++){
            rites[i] = rituals[ritualId].rite[i];
        }
        return rites;
    }

    function initiateRitual(address[] calldata nodes) external returns (uint32) {
        require(nodes.length <= maxDkgSize, "Invalid number of nodes");

        uint32 id = uint32(rituals.length);
        Ritual storage ritual = rituals.push();
        ritual.id = id;
        ritual.initiator = msg.sender;
        ritual.threshold = threshold;
        ritual.dkgSize = uint32(nodes.length);
        ritual.initTimestamp = uint32(block.timestamp);
        ritual.status = RitualStatus.WAITING_FOR_TRANSCRIPTS;

        address previousNode = nodes[0];
        ritual.rite[0].node = previousNode;
        address currentNode;
        for(uint256 i=1; i < nodes.length; i++){
            currentNode = nodes[i];
            ritual.rite[i].node = currentNode;
            previousNode = currentNode;
            // TODO: Check nodes are eligible (staking, etc)
        }

        emit StartRitual(id, nodes, msg.sender);
        return ritual.id;
    }

    function postTranscript(uint32 ritualId, uint256 nodeIndex, bytes calldata transcript) external {
        Ritual storage ritual = rituals[ritualId];
        require(ritual.rite[nodeIndex].node == msg.sender, "Node not part of ritual");
        require(ritual.status == RitualStatus.WAITING_FOR_TRANSCRIPTS, "Not waiting for transcripts");
        require(ritual.rite[nodeIndex].transcript.length == 0, "Node already posted transcript");
        require(ritual.rite[nodeIndex].aggregated == false, "Node already posted aggregation");
        _checkActiveRitual(ritual);

        // Nodes commit to their transcript
        bytes32 transcriptDigest = keccak256(transcript);
        ritual.rite[nodeIndex].transcript = transcript;
        emit TranscriptPosted(ritualId, msg.sender, transcriptDigest);
        ritual.totalTranscripts++;

        // end round
        if (ritual.totalTranscripts == ritual.dkgSize){
            ritual.status = RitualStatus.WAITING_FOR_AGGREGATIONS;
            emit StartAggregationRound(ritualId);
        }
    }

    function postAggregation(uint32 ritualId, uint256 nodeIndex, bytes calldata aggregatedTranscripts) external {
        Ritual storage ritual = rituals[ritualId];
        require(ritual.status == RitualStatus.WAITING_FOR_AGGREGATIONS, "Not waiting for confirmations");
        require(ritual.rite[nodeIndex].node == msg.sender, "Node not part of ritual");
        _checkActiveRitual(ritual);

        // nodes commit to their aggregation result
        bytes32 aggregatedTranscriptDigest = keccak256(aggregatedTranscripts);
        ritual.rite[nodeIndex].transcript = aggregatedTranscriptDigest;
        ritual.rite[nodeIndex].aggregated = true;
        emit AggregationPosted(ritualId, msg.sender, aggregatedTranscripts);
        ritual.totalAggregations++;

        // end round
        if (ritual.totalAggregations == ritual.dkgSize){
            ritual.status = RitualStatus.WAITING_FOR_FINALIZATION;
            emit EndRitual(ritualId, ritual.status, ritual.initiator);
        }
    }

    function finalizeRitual(uint32 ritualId) public {
        Ritual storage ritual = rituals[ritualId];
        require(ritual.status == RitualStatus.WAITING_FOR_FINALIZATION, 'ritual cannot be finalized');

        bytes32 firstRiteDigest = keccak256(ritual.rite[0].transcript);
        for(uint32 i=1; i < ritual.rite.length; i++){
            bytes32 currentRiteDigest = keccak256(ritual.rite[i].transcript);
            if (firstRiteDigest != currentRiteDigest) {
                ritual.status = RitualStatus.FAILED_INVALID_TRANSCRIPTS;
                emit EndRitual(ritualId, ritual.status, ritual.initiator);
                revert('aggregated transcripts do not match');
            }
        }

        ritual.publicMaterial = firstRiteDigest;
        ritual.status = RitualStatus.FINALIZED;
        emit EndRitual(ritualId, ritual.status, ritual.initiator);
    }

}
