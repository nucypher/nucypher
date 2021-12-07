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
        WorkLockInterface _workLock
    )
        StakingEscrow(
            _token,
            _workLock
        )
    {
    }

    function testSlashStaker(
        address _staker,
        uint256 _penalty,
        address _investigator,
        uint256 _reward
    )
        external
    {
        slashStaker(_staker, _penalty, _investigator, _reward);
    }

    function setStaker(address _staker, uint256 _value, uint16 _lastCommittedPeriod) external {
        StakerInfo storage info = stakerInfo[_staker];
        info.value = _value;
        info.lastCommittedPeriod = _lastCommittedPeriod;
        stakers.push(_staker);
    }

}


/**
* @notice Upgrade to this contract must lead to fail
*/
contract StakingEscrowBad is StakingEscrow {

    constructor(
        NuCypherToken _token,
        WorkLockInterface _workLock
    )
        StakingEscrow(
            _token,
            _workLock
        )
    {
    }

    function getStakersLength() external override view returns (uint256) {}

}


/**
* @notice Contract for testing upgrading the StakingEscrow contract
*/
contract StakingEscrowV2Mock is StakingEscrow {

    uint256 public valueToCheck;

    constructor(
        NuCypherToken _token,
        WorkLockInterface _workLock
    )
        StakingEscrow(
            _token,
            _workLock
        )
    {
        valueToCheck = 2;
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


///**
//* @notice Intermediary contract for testing worker
//*/
//contract Intermediary { // TODO move to app tests
//
//    NuCypherToken immutable token;
//    StakingEscrow immutable escrow;
//
//    constructor(NuCypherToken _token, StakingEscrow _escrow) {
//        token = _token;
//        escrow = _escrow;
//    }
//
//    function bondWorker(address _worker) external {
//        escrow.bondWorker(_worker);
//    }
//
//}


/**
* @notice Contract for testing staking escrow contract
*/
contract WorkLockForStakingEscrowMock {

    NuCypherToken public immutable token;
    StakingEscrow public escrow;

    constructor(NuCypherToken _token) {
        token = _token;
    }

    function setStakingEscrow(StakingEscrow _escrow) external {
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
