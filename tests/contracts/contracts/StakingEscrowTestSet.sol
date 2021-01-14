// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


import "contracts/StakingEscrow.sol";
import "contracts/NuCypherToken.sol";

/**
* @notice Enhanced version of StakingEscrow to use in tests
*/
contract EnhancedStakingEscrow is StakingEscrow {
    using AdditionalMath for uint16;

    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _issuanceDecayCoefficient,
        uint256 _lockDurationCoefficient1,
        uint256 _lockDurationCoefficient2,
        uint16 _maximumRewardedPeriods,
        uint256 _firstPhaseTotalSupply,
        uint256 _firstPhaseMaxIssuance,
        uint16 _minLockedPeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens,
        uint16 _minWorkerPeriods
    )
        StakingEscrow(
            _token,
            _hoursPerPeriod,
            _issuanceDecayCoefficient,
            _lockDurationCoefficient1,
            _lockDurationCoefficient2,
            _maximumRewardedPeriods,
            _firstPhaseTotalSupply,
            _firstPhaseMaxIssuance,
            _minLockedPeriods,
            _minAllowableLockedTokens,
            _maxAllowableLockedTokens,
            _minWorkerPeriods
        )
    {
    }

    /**
    * @notice Get the value of locked tokens for a staker in a previous period
    * @dev Information may be incorrect for rewarded or not committed surpassed period
    * @param _staker Staker
    * @param _periods Amount of periods that will be subtracted from the current period
    */
    function getLockedTokensInPast(address _staker, uint16 _periods)
        external view returns (uint256 lockedValue)
    {
        StakerInfo storage info = stakerInfo[_staker];
        uint16 currentPeriod = getCurrentPeriod();
        uint16 previousPeriod = currentPeriod.sub16(_periods);
        return getLockedTokens(info, currentPeriod, previousPeriod);
    }

}


/**
* @notice Upgrade to this contract must lead to fail
*/
contract StakingEscrowBad is StakingEscrow {

    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _issuanceDecayCoefficient,
        uint256 _lockDurationCoefficient1,
        uint256 _lockDurationCoefficient2,
        uint16 _maximumRewardedPeriods,
        uint256 _firstPhaseTotalSupply,
        uint256 _firstPhaseMaxIssuance,
        uint16 _minLockedPeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens,
        uint16 _minWorkerPeriods
    )
        StakingEscrow(
            _token,
            _hoursPerPeriod,
            _issuanceDecayCoefficient,
            _lockDurationCoefficient1,
            _lockDurationCoefficient2,
            _maximumRewardedPeriods,
            _firstPhaseTotalSupply,
            _firstPhaseMaxIssuance,
            _minLockedPeriods,
            _minAllowableLockedTokens,
            _maxAllowableLockedTokens,
            _minWorkerPeriods
        )
    {
    }

    function getSubStakeInfo(address, uint256) public view override returns (uint16, uint16, uint16, uint128) {}

}


/**
* @notice Contract for testing upgrading the StakingEscrow contract
*/
contract StakingEscrowV2Mock is StakingEscrow {

    uint256 public valueToCheck;

    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _issuanceDecayCoefficient,
        uint256 _lockDurationCoefficient1,
        uint256 _lockDurationCoefficient2,
        uint16 _maximumRewardedPeriods,
        uint256 _firstPhaseTotalSupply,
        uint256 _firstPhaseMaxIssuance,
        uint16 _minLockedPeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens,
        uint16 _minWorkerPeriods,
        uint256 _valueToCheck
    )
        StakingEscrow(
            _token,
            _hoursPerPeriod,
            _issuanceDecayCoefficient,
            _lockDurationCoefficient1,
            _lockDurationCoefficient2,
            _maximumRewardedPeriods,
            _firstPhaseTotalSupply,
            _firstPhaseMaxIssuance,
            _minLockedPeriods,
            _minAllowableLockedTokens,
            _maxAllowableLockedTokens,
            _minWorkerPeriods
        )
    {
        valueToCheck = _valueToCheck;
    }

    function setValueToCheck(uint256 _valueToCheck) public {
        valueToCheck = _valueToCheck;
    }

    function verifyState(address _testTarget) public override {
        super.verifyState(_testTarget);
        require(delegateGet(_testTarget, this.valueToCheck.selector) == valueToCheck);
    }

    function finishUpgrade(address _target) public override onlyWhileUpgrading {
        StakingEscrowV2Mock escrow = StakingEscrowV2Mock(_target);
        valueToCheck = escrow.valueToCheck();
        emit UpgradeFinished(_target, msg.sender);
    }
}


/**
* @notice Contract for testing staking escrow contract
*/
contract PolicyManagerForStakingEscrowMock {

    StakingEscrow public immutable escrow;
    mapping (address => uint16[]) public nodes;

    constructor(address, StakingEscrow _escrow) {
        escrow = _escrow;
    }

    function register(address _node, uint16 _period) external {
        nodes[_node].push(_period);
    }

    function ping(
        address _node,
        uint16 _processedPeriod1,
        uint16 _processedPeriod2,
        uint16 _periodToSetDefault
    ) external {
        nodes[_node].push(_processedPeriod1);
        nodes[_node].push(_processedPeriod2);
        nodes[_node].push(_periodToSetDefault);
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

    StakingEscrow public immutable escrow;

    constructor(StakingEscrow _escrow) {
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

    NuCypherToken immutable token;
    StakingEscrow immutable escrow;

    constructor(NuCypherToken _token, StakingEscrow _escrow) {
        token = _token;
        escrow = _escrow;
    }

    function bondWorker(address _worker) external {
        escrow.bondWorker(_worker);
    }

    function deposit(uint256 _value, uint16 _periods) external {
        token.approve(address(escrow), _value);
        escrow.deposit(address(this), _value, _periods);
    }

    function commitToNextPeriod() external {
        escrow.commitToNextPeriod();
    }

}


/**
* @notice Contract for testing staking escrow contract
*/
contract WorkLockForStakingEscrowMock {

    NuCypherToken public immutable token;
    StakingEscrow public immutable escrow;

    constructor(NuCypherToken _token, StakingEscrow _escrow) {
        token = _token;
        escrow = _escrow;
    }

    function setWorkMeasurement(address _staker, bool _measureWork) external returns (uint256) {
        return escrow.setWorkMeasurement(_staker, _measureWork);
    }

    function depositFromWorkLock(address _staker, uint256 _value, uint16 _periods) external {
        token.approve(address(escrow), _value);
        escrow.depositFromWorkLock(_staker, _value, _periods);
    }
}
