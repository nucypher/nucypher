// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


import "contracts/NuCypherToken.sol";


/**
* @notice Contract for using in WorkLock tests
*/
contract StakingEscrowForWorkLockMock {

    struct StakerInfo {
        uint256 value;
        bool measureWork;
        uint256 completedWork;
        uint16 periods;
    }

    NuCypherToken public immutable token;
    uint32 public immutable secondsPerPeriod = 1;
    uint256 public immutable minAllowableLockedTokens;
    uint256 public immutable maxAllowableLockedTokens;
    uint16 public immutable minLockedPeriods;

    mapping (address => StakerInfo) public stakerInfo;

    constructor(
        NuCypherToken _token,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens,
        uint16 _minLockedPeriods
    ) {
        token = _token;
        minAllowableLockedTokens = _minAllowableLockedTokens;
        maxAllowableLockedTokens = _maxAllowableLockedTokens;
        minLockedPeriods = _minLockedPeriods;
    }

    function getCompletedWork(address _staker) external view returns (uint256) {
        return stakerInfo[_staker].completedWork;
    }

    function setWorkMeasurement(address _staker, bool _measureWork) external returns (uint256) {
        stakerInfo[_staker].measureWork = _measureWork;
        return stakerInfo[_staker].completedWork;
    }

    function depositFromWorkLock(address _staker, uint256 _value, uint16 _periods) external {
        stakerInfo[_staker].value = _value;
        stakerInfo[_staker].periods = _periods;
        token.transferFrom(msg.sender, address(this), _value);
    }

    function setCompletedWork(address _staker, uint256 _completedWork) external {
        stakerInfo[_staker].completedWork = _completedWork;
    }

}
