// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


import "contracts/PolicyManager.sol";
import "contracts/StakingEscrow.sol";


/**
* @notice Upgrade to this contract must lead to fail
*/
contract PolicyManagerBad is PolicyManager {

    constructor(StakingEscrow _escrow) PolicyManager(_escrow) {
    }

    function getNodeFeeDelta(address, uint16) public view override returns (int256) {}

}


/**
* @notice Contract for testing upgrading the PolicyManager contract
*/
contract PolicyManagerV2Mock is PolicyManager {

    uint256 public valueToCheck;

    constructor(StakingEscrow _escrow) PolicyManager(_escrow) {
    }

    function setValueToCheck(uint256 _valueToCheck) public {
        valueToCheck = _valueToCheck;
    }

    function verifyState(address _testTarget) public override {
        super.verifyState(_testTarget);
        require(delegateGet(_testTarget, this.valueToCheck.selector) == valueToCheck);
    }
}


/**
* @notice Contract for using in PolicyManager tests
*/
contract StakingEscrowForPolicyMock {

    struct Downtime {
        uint16 startPeriod;
        uint16 endPeriod;
    }

    uint32 public immutable secondsPerPeriod;

    PolicyManager public policyManager;
    uint16 public lastCommittedPeriod;
    Downtime[] public downtime;

    /**
    * @param _hoursPerPeriod Size of period in hours
    */
    constructor(uint16 _hoursPerPeriod) {
        secondsPerPeriod = uint32(_hoursPerPeriod * 1 hours);
    }

    /**
    * @return Number of current period
    */
    function getCurrentPeriod() public view returns (uint16) {
        return uint16(block.timestamp / secondsPerPeriod);
    }

    /**
    * @notice Set last committed period
    */
    function setLastCommittedPeriod(uint16 _lastCommittedPeriod) external {
        lastCommittedPeriod = _lastCommittedPeriod;
    }

    /**
    * @notice Add downtime period
    */
    function pushDowntimePeriod(uint16 _startPeriod, uint16 _endPeriod) external {
        downtime.push(Downtime(_startPeriod, _endPeriod));
    }

    /**
    * @notice Emulate ping method call
    */
    function ping(
        address _node,
        uint16 _processedPeriod1,
        uint16 _processedPeriod2,
        uint16 _periodToSetDefault
    ) external {
        policyManager.ping(_node, _processedPeriod1, _processedPeriod2, _periodToSetDefault);
    }

    /**
    * @notice Set policy manager address
    */
    function setPolicyManager(PolicyManager _policyManager) external {
        policyManager = _policyManager;
    }

    function getPastDowntimeLength(address) public view returns (uint256) {
        return downtime.length;
    }

    function getPastDowntime(address, uint256 _index)
        public view returns (uint16 startPeriod, uint16 endPeriod)
    {
        Downtime storage data = downtime[_index];
        startPeriod = data.startPeriod;
        endPeriod = data.endPeriod;
    }

    function getLastCommittedPeriod(address) public view returns (uint256) {
        return lastCommittedPeriod;
    }

    function register(address _node, uint16 _period) public {
        policyManager.register(_node, _period);
    }

    function register(address _node) external {
        register(_node, getCurrentPeriod() - 1);
    }

    function findIndexOfPastDowntime(address, uint16 _period) external view returns (uint256 index) {
        for (index = 0; index < downtime.length; index++) {
            if (_period <= downtime[index].endPeriod) {
                return index;
            }
        }
    }

}


/**
* @notice Helper to prepare broken state
*/
contract ExtendedPolicyManager is PolicyManager {

    constructor(StakingEscrow _escrow) PolicyManager(_escrow) {
    }

    function setNodeFeeDelta(address _node, uint16 _period, int256 _value) external {
        NodeInfo storage node = nodes[_node];
        node.feeDelta[_period] = _value;
    }
}
