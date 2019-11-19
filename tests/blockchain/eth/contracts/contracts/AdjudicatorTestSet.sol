pragma solidity ^0.5.3;


import "contracts/Adjudicator.sol";
import "contracts/StakingEscrow.sol";
import "contracts/lib/SignatureVerifier.sol";
import "contracts/proxy/Upgradeable.sol";


/**
* @notice Contract for testing the Adjudicator contract
*/
contract StakingEscrowForAdjudicatorMock {

    uint32 public secondsPerPeriod = 1;
    mapping (address => uint256) public stakerInfo;
    mapping (address => uint256) public rewardInfo;
    mapping (address => address) public workerToStaker;

    function setStakerInfo(address _staker, uint256 _amount, address _worker) public {
        stakerInfo[_staker] = _amount;
        if (_worker == address(0)) {
            _worker = _staker;
        }
        workerToStaker[_worker] = _staker;
    }

    function getAllTokens(address _staker) public view returns (uint256) {
        return stakerInfo[_staker];
    }

    function getStakerFromWorker(address _worker) public view returns (address) {
        return workerToStaker[_worker];
    }

    function slashStaker(
        address _staker,
        uint256 _penalty,
        address _investigator,
        uint256 _reward
    )
        public
    {
        stakerInfo[_staker] -= _penalty;
        rewardInfo[_investigator] += _reward;
    }

}


/**
* @notice Upgrade to this contract must lead to fail
*/
contract AdjudicatorBad is Upgradeable {

    StakingEscrow public escrow;
    SignatureVerifier.HashAlgorithm public hashAlgorithm;
    uint256 public basePenalty;
    uint256 public penaltyHistoryCoefficient;
    uint256 public percentagePenalty;
    uint256 public rewardCoefficient;
    mapping (bytes32 => bool) public evaluatedCFrags;
    mapping (address => uint256) public penaltyHistory;

}


/**
* @notice Contract for testing upgrading the Adjudicator contract
*/
contract AdjudicatorV2Mock is Adjudicator {

    uint256 public valueToCheck;

    constructor(
        StakingEscrow _escrow,
        SignatureVerifier.HashAlgorithm _hashAlgorithm,
        uint256 _basePenalty,
        uint256 _percentagePenalty,
        uint256 _penaltyHistoryCoefficient,
        uint256 _rewardCoefficient
    )
        public
        Adjudicator(
            _escrow,
            _hashAlgorithm,
            _basePenalty,
            _percentagePenalty,
            _penaltyHistoryCoefficient,
            _rewardCoefficient
        )
    {
    }

    function setValueToCheck(uint256 _valueToCheck) public {
        valueToCheck = _valueToCheck;
    }

    function verifyState(address _testTarget) public {
        super.verifyState(_testTarget);
        require(uint256(delegateGet(_testTarget, "valueToCheck()")) == valueToCheck);
    }
}
