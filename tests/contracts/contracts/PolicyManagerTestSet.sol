// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "contracts/PolicyManager.sol";
import "contracts/PREStakingApp.sol";


/**
* @notice Upgrade to this contract must lead to fail
*/
contract PolicyManagerBad is PolicyManager {

    constructor(PREStakingApp _stakingApp) PolicyManager(_stakingApp) {
    }

    function getNodeFeeDelta(address, uint16) public view override returns (int256) {}

}


/**
* @notice Contract for testing upgrading the PolicyManager contract
*/
contract PolicyManagerV2Mock is PolicyManager {

    uint256 public valueToCheck;

    constructor(PREStakingApp _stakingApp) PolicyManager(_stakingApp) {
    }

    function setValueToCheck(uint256 _valueToCheck) public {
        valueToCheck = _valueToCheck;
    }

    function verifyState(address _testTarget) public override {
        super.verifyState(_testTarget);
        require(delegateGet(_testTarget, this.valueToCheck.selector) == valueToCheck);
    }
}

// TODO PREStakingAPP mock


/**
* @notice Helper to prepare broken state
*/
contract ExtendedPolicyManager is PolicyManager {

    constructor(PREStakingApp _stakingApp) PolicyManager(_stakingApp) {
    }

    function setNodeFeeDelta(address _node, uint16 _period, int256 _value) external {
        NodeInfo storage node = nodes[_node];
        node.feeDelta[_period] = _value;
    }
}
