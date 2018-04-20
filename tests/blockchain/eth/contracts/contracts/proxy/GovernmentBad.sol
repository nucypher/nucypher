pragma solidity ^0.4.18;


import "proxy/Upgradeable.sol";


/**
* @notice Contract for using in Government tests
**/
contract GovernmentBad is Upgradeable {

    enum VotingType {
        UpgradeGovernment,
        UpgradeEscrow,
        UpgradePolicyManager,
        RollbackGovernment,
        RollbackEscrow,
        RollbackPolicyManager
    }

    address public escrow;
    address public policyManager;
    uint256 public votingDurationSeconds;

    mapping(address => uint256) public lastVote;
//    uint256 public votingNumber;
    uint256 public endVotingTimestamp;
    bool public upgradeFinished;
    VotingType public votingType;
    address public newAddress;
    uint256 public votesFor;
    uint256 public votesAgainst;

    function verifyState(address) public {}
    function finishUpgrade(address) public {}
}
