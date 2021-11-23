// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


contract OldPolicyManagerMock {
    uint32 public immutable secondsPerPeriod = 1 hours;

    function register(address _node, uint16 _period) external {}
}


contract OldAdjudicatorMock {
    uint256 public immutable rewardCoefficient = 1;
}
