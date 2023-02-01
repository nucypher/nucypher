// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;

/**
* @title CoordinatorV1
* @notice Coordination layer for DKG-TDec
*/
contract CoordinatorV1 {

    uint32 public constant DKG_SIZE = 8;
    uint32 public TIMEOUT = 9600;

    event StartRitual(uint32 indexed ritualId, address[] nodes);
    event StartTranscriptRound(uint32 indexed ritualId);
    event StartConfirmationRound(uint32 indexed ritualId);
    event RitualEnded(uint32 indexed ritualId);

    event TranscriptPosted(uint32 indexed ritualId, address indexed node, bytes32 transcriptDigest);
    event ConfirmationPosted(uint32 indexed ritualId, address indexed node, address[] confirmedNodes);

    event TimeoutChanged(uint32 timeout);
    event DkgSizeChanged(uint8 dkgSize);

    enum RitualStatus {
        WAITING_FOR_CHECKINS,
        WAITING_FOR_TRANSCRIPTS,
        WAITING_FOR_CONFIRMATIONS,
        COMPLETED,
        FAILED
    }

    // TODO: Find better name
    struct Performance {
        address node;
        uint32 checkinTimestamp;
        uint96 confirmedBy;
        bytes32 transcript;
    }

    struct Ritual {
        uint32 id;
        uint32 initTimestamp;
        uint32 totalCheckins;
        uint32 totalTranscripts;
        uint32 totalConfirmations;
        RitualStatus status;
        Performance[DKG_SIZE] performance;
    }

    Ritual[] public rituals;

    function numberOfRituals() external view returns(uint256){
        return rituals.length;
    }

    function getPerformances(uint32 ritualId) external view returns(Performance[] memory){
        Performance[] memory performances = new Performance[](rituals[ritualId].performance.length);
        for(uint32 i=0; i < rituals[ritualId].performance.length; i++){
            performances[i] = rituals[ritualId].performance[i];
        }
        return performances;
    }

    function setTimeout(uint32 timeout) external {
        TIMEOUT = timeout;
        emit TimeoutChanged(timeout);
    }

    function initiateRitual(address[] calldata nodes) external {
        // TODO: Check for payment
        // TODO: Check for expiration time
        // TODO: Improve DKG size choices
        require(nodes.length == DKG_SIZE, "Invalid number of nodes");

        uint32 id = uint32(rituals.length);
        Ritual storage ritual = rituals.push();
        ritual.id = id;
        ritual.initTimestamp = uint32(block.timestamp);
        ritual.status = RitualStatus.WAITING_FOR_CHECKINS;
        ritual.totalTranscripts = 0;
        ritual.totalConfirmations = 0;
        ritual.totalCheckins = 0;

        address previousNode = nodes[0];
        ritual.performance[0].node = previousNode;
        address currentNode;
        for(uint256 i=1; i < nodes.length; i++){
            currentNode = nodes[i];
            require(currentNode > previousNode, "Nodes must be sorted");
            ritual.performance[i].node = currentNode;
            previousNode = currentNode;
            // TODO: Check nodes are eligible (staking, etc)
        }

        emit StartRitual(id, nodes);
    }

    function checkIn(uint32 ritualId, uint256 nodeIndex) external {
        Ritual storage ritual = rituals[ritualId];
        require(ritual.status == RitualStatus.WAITING_FOR_CHECKINS, "Not waiting for check-ins");
        require(ritual.performance[nodeIndex].node == msg.sender, "Node not part of ritual");
        if ((uint32(block.timestamp) - ritual.initTimestamp) > TIMEOUT) {
            ritual.status = RitualStatus.FAILED;
            emit RitualEnded(ritualId);
            revert("Ritual timed out");
        }
        require(ritual.performance[nodeIndex].checkinTimestamp == 0, "Node already checked in");
        ritual.performance[nodeIndex].checkinTimestamp = uint32(block.timestamp);
        ritual.totalCheckins++;
        if (ritual.totalCheckins == DKG_SIZE){
            ritual.status = RitualStatus.WAITING_FOR_TRANSCRIPTS;
            emit StartTranscriptRound(ritualId);
        }
    }

    function postTranscript(uint32 ritualId, uint256 nodeIndex, bytes calldata transcript) external {
        Ritual storage ritual = rituals[ritualId];
        require(ritual.status == RitualStatus.WAITING_FOR_TRANSCRIPTS, "Not waiting for transcripts");
        require(ritual.performance[nodeIndex].node == msg.sender, "Node not part of ritual");
        if ((uint32(block.timestamp) - ritual.initTimestamp) > TIMEOUT) {
            ritual.status = RitualStatus.FAILED;
            emit RitualEnded(ritualId);
            revert("Ritual timed out");
        }
        require(ritual.performance[nodeIndex].transcript == bytes32(0), "Node already posted transcript");

        // Nodes commit to their transcript
        bytes32 transcriptDigest = keccak256(transcript);
        ritual.performance[nodeIndex].transcript = transcriptDigest;
        ritual.totalTranscripts++;
        if (ritual.totalTranscripts == DKG_SIZE){
            ritual.status = RitualStatus.WAITING_FOR_CONFIRMATIONS;
            emit StartConfirmationRound(ritualId);
        }
        emit TranscriptPosted(ritualId, msg.sender, transcriptDigest);
    }

    function postConfirmation(uint32 ritualId, uint256 nodeIndex, uint256[] calldata confirmedNodesIndexes) external {
        Ritual storage ritual = rituals[ritualId];
        require(ritual.status == RitualStatus.WAITING_FOR_CONFIRMATIONS, "Not waiting for confirmations");
        require(
            ritual.performance[nodeIndex].node == msg.sender &&
            ritual.performance[nodeIndex].transcript != bytes32(0),
            "Node not part of ritual"
        );

        require(confirmedNodesIndexes.length <= DKG_SIZE, "Invalid number of confirmations");
        if ((uint32(block.timestamp) - ritual.initTimestamp) > TIMEOUT) {
            ritual.status = RitualStatus.FAILED;
            emit RitualEnded(ritualId);
            revert("Ritual timed out");
        }

        address[] memory confirmedNodes = new address[](confirmedNodesIndexes.length);

        // First, node adds itself to its list of confirmers
        uint96 caller = uint96(2 ** nodeIndex);
        ritual.performance[nodeIndex].confirmedBy |= caller;
        for(uint256 i=0; i < confirmedNodesIndexes.length; i++){
            uint256 confirmedNodeIndex = confirmedNodesIndexes[i];
            require(confirmedNodeIndex < DKG_SIZE, "Invalid node index");
            // We add caller to the list of confirmations of each confirmed node
            ritual.performance[confirmedNodeIndex].confirmedBy |= caller;
            confirmedNodes[i] = ritual.performance[confirmedNodeIndex].node;
        }
        ritual.totalConfirmations++;
        if (ritual.totalConfirmations == DKG_SIZE){
            ritual.status = RitualStatus.COMPLETED;
            emit RitualEnded(ritualId);
        }
        emit ConfirmationPosted(ritualId, msg.sender, confirmedNodes);
    }

}