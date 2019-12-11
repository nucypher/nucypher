pragma solidity ^0.5.3;


import "contracts/StakingEscrow.sol";
import "contracts/NuCypherToken.sol";


/**
* @notice Upgrade to this contract must lead to fail
*/
contract StakingEscrowBad is StakingEscrow {

    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint16 _rewardedPeriods,
        uint16 _minLockedPeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens,
        uint16 _minWorkerPeriods,
        bool _isTestContract
    )
        public
        StakingEscrow(
            _token,
            _hoursPerPeriod,
            _miningCoefficient,
            _lockedPeriodsCoefficient,
            _rewardedPeriods,
            _minLockedPeriods,
            _minAllowableLockedTokens,
            _maxAllowableLockedTokens,
            _minWorkerPeriods,
            _isTestContract
        )
    {
    }

    function getSubStakeInfo(address, uint256) public view returns (uint16, uint16, uint16, uint256)
    {
    }

}


/**
* @notice Contract for testing upgrading the StakingEscrow contract
*/
contract StakingEscrowV2Mock is StakingEscrow {

    uint256 public valueToCheck;

    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint16 _rewardedPeriods,
        uint16 _minLockedPeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens,
        uint16 _minWorkerPeriods,
        bool _isTestContract,
        uint256 _valueToCheck
    )
        public
        StakingEscrow(
            _token,
            _hoursPerPeriod,
            _miningCoefficient,
            _lockedPeriodsCoefficient,
            _rewardedPeriods,
            _minLockedPeriods,
            _minAllowableLockedTokens,
            _maxAllowableLockedTokens,
            _minWorkerPeriods,
            _isTestContract
        )
    {
        valueToCheck = _valueToCheck;
    }

    function setValueToCheck(uint256 _valueToCheck) public {
        valueToCheck = _valueToCheck;
    }

    function verifyState(address _testTarget) public {
        super.verifyState(_testTarget);
        require(delegateGet(_testTarget, "valueToCheck()") == valueToCheck);
    }

    function finishUpgrade(address _target) public onlyWhileUpgrading {
        StakingEscrowV2Mock escrow = StakingEscrowV2Mock(_target);
        valueToCheck = escrow.valueToCheck();
        isTestContract = escrow.isTestContract();
        emit UpgradeFinished(_target, msg.sender);
    }
}


/**
* @notice Contract for testing staking escrow contract
*/
contract PolicyManagerForStakingEscrowMock {

    StakingEscrow public escrow;
    mapping (address => uint16[]) public nodes;

    constructor(address, StakingEscrow _escrow) public {
        escrow = _escrow;
    }

    function register(address _node, uint16 _period) external {
        nodes[_node].push(_period);
    }

    function updateReward(address _node, uint16 _period) external {
        nodes[_node].push(_period);
    }

    function setDefaultRewardDelta(address _node, uint16 _period) external {
        nodes[_node].push(_period);
    }

    function getPeriodsLength(address _node) public view returns (uint256) {
        return nodes[_node].length;
    }

    function getPeriod(address _node, uint256 _index) public view returns (uint16) {
        return nodes[_node][_index];
    }

}


/**
* @notice Contract for testing staking escrow contract
*/
contract AdjudicatorForStakingEscrowMock {

    StakingEscrow public escrow;

    constructor(StakingEscrow _escrow) public {
        escrow = _escrow;
    }

    function slashStaker(
        address _staker,
        uint256 _penalty,
        address _investigator,
        uint256 _reward
    )
        public
    {
        escrow.slashStaker(_staker, _penalty, _investigator, _reward);
    }
}

/**
* @notice Intermediary contract for testing worker
*/
contract Intermediary {

    NuCypherToken token;
    StakingEscrow escrow;

    constructor(NuCypherToken _token, StakingEscrow _escrow) public {
        token = _token;
        escrow = _escrow;
    }

    function setWorker(address _worker) public {
        escrow.setWorker(_worker);
    }

    function deposit(uint256 _value, uint16 _periods) public {
        token.approve(address(escrow), _value);
        escrow.deposit(_value, _periods);
    }

    function confirmActivity() public {
        escrow.confirmActivity();
    }

}


/**
* @notice Contract for testing staking escrow contract
*/
contract WorkLockForStakingEscrowMock {

    StakingEscrow public escrow;

    constructor(StakingEscrow _escrow) public {
        escrow = _escrow;
    }

    function setWorkMeasurement(address _staker, bool _measureWork) public returns (uint256) {
        return escrow.setWorkMeasurement(_staker, _measureWork);
    }
}

