// SPDX-License-Identifier: GPL-3.0-or-later

pragma solidity ^0.7.0;

import "./IForwarder.sol";

// Interface for Voting contract, as found in https://github.com/aragon/aragon-apps/blob/master/apps/voting/contracts/Voting.sol
interface Voting is IForwarder{

    enum VoterState { Absent, Yea, Nay }

    // Public getters
    function token() external returns (address);
    function supportRequiredPct() external returns (uint64);
    function minAcceptQuorumPct() external returns (uint64);
    function voteTime() external returns (uint64);
    function votesLength() external returns (uint256);

    // Setters
    function changeSupportRequiredPct(uint64 _supportRequiredPct) external;
    function changeMinAcceptQuorumPct(uint64 _minAcceptQuorumPct) external;

    // Creating new votes
    function newVote(bytes calldata _executionScript, string memory _metadata) external returns (uint256 voteId);
    function newVote(bytes calldata _executionScript, string memory _metadata, bool _castVote, bool _executesIfDecided)
        external returns (uint256 voteId);

    // Voting
    function canVote(uint256 _voteId, address _voter) external view returns (bool);
    function vote(uint256 _voteId, bool _supports, bool _executesIfDecided) external;

    // Executing a passed vote
    function canExecute(uint256 _voteId) external view returns (bool);
    function executeVote(uint256 _voteId) external;

    // Additional info
    function getVote(uint256 _voteId) external view
        returns (
            bool open,
            bool executed,
            uint64 startDate,
            uint64 snapshotBlock,
            uint64 supportRequired,
            uint64 minAcceptQuorum,
            uint256 yea,
            uint256 nay,
            uint256 votingPower,
            bytes memory script
        );
    function getVoterState(uint256 _voteId, address _voter) external view returns (VoterState);

}
