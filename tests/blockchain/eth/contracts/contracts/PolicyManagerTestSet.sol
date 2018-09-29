pragma solidity ^0.4.24;


import "contracts/PolicyManager.sol";
import "contracts/MinersEscrow.sol";


/**
* @notice Upgrade to this contract must lead to fail
**/
contract PolicyManagerBad is PolicyManager {

    constructor(MinersEscrow _escrow) public PolicyManager(_escrow) {
    }

    function getNodeRewardDelta(address, uint16) public view returns (int256)
    {
    }

}


/**
* @notice Contract for testing upgrading the PolicyManager contract
**/
contract PolicyManagerV2Mock is PolicyManager {

    uint256 public valueToCheck;

    constructor(MinersEscrow _escrow) public PolicyManager(_escrow) {
    }

    function setValueToCheck(uint256 _valueToCheck) public {
        valueToCheck = _valueToCheck;
    }

    function verifyState(address _testTarget) public onlyOwner {
        super.verifyState(_testTarget);
        require(uint256(delegateGet(_testTarget, "valueToCheck()")) == valueToCheck);
    }
}


/**
* @notice Contract for using in PolicyManager tests
**/
contract MinersEscrowForPolicyMock {

    struct Downtime {
        uint16 startPeriod;
        uint16 endPeriod;
    }

    PolicyManager public policyManager;
    uint32 public secondsPerPeriod;
    uint16 public lastActivePeriod;
    Downtime[] public downtime;

    /**
    * @param _hoursPerPeriod Size of period in hours
    **/
    constructor(uint16 _hoursPerPeriod) public {
        secondsPerPeriod = uint32(_hoursPerPeriod * 1 hours);
    }

    /**
    * @return Number of current period
    **/
    function getCurrentPeriod() public view returns (uint16) {
        return uint16(block.timestamp / secondsPerPeriod);
    }

    /**
    * @notice Set last active period
    **/
    function setLastActivePeriod(uint16 _lastActivePeriod) external {
        lastActivePeriod = _lastActivePeriod;
    }

    /**
    * @notice Add downtime period
    **/
    function pushDowntimePeriod(uint16 _startPeriod, uint16 _endPeriod) external {
        downtime.push(Downtime(_startPeriod, _endPeriod));
    }

    /**
    * @notice Emulate mint method
    * @param _startPeriod Start period for minting
    * @param _numberOfPeriods Number periods for minting
    **/
    function mint(uint16 _startPeriod, uint16 _numberOfPeriods) external {
        for (uint16 i = 0; i < _numberOfPeriods; i++) {
            policyManager.updateReward(msg.sender, i + _startPeriod);
        }
    }

    /**
    * @notice Set policy manager address
    **/
    function setPolicyManager(PolicyManager _policyManager) external {
        policyManager = _policyManager;
    }

    /**
    * @notice Emulate getDowntimeLength
    **/
    function getPastDowntimeLength(address) public view returns (uint256) {
        return downtime.length;
    }

    /**
    * @notice Emulate getDowntime
    **/
    function getPastDowntime(address, uint256 _index)
        public view returns (uint16 startPeriod, uint16 endPeriod)
    {
        Downtime storage data = downtime[_index];
        startPeriod = data.startPeriod;
        endPeriod = data.endPeriod;
    }

    /**
    * @notice Emulate getLastActivePeriod
    **/
    function getLastActivePeriod(address) public view returns (uint256) {
        return lastActivePeriod;
    }

    /**
    * @notice Emulate node registration
    **/
    function register(address _node) external {
        policyManager.register(_node, getCurrentPeriod() - 1);
    }
}