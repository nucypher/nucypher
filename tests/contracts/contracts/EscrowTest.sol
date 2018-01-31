pragma solidity ^0.4.8;


import "contracts/PolicyManager.sol";


/**
* @notice Contract for testing PolicyManager contract
**/
contract EscrowTest {

    struct Downtime {
        uint256 startPeriod;
        uint256 endPeriod;
    }

    PolicyManager policyManager;
    uint256 public secondsPerPeriod;
    address node;
    uint256 lastActivePeriod;
    Downtime[] downtime;

    /**
    * @param _node Address of node that allow to use policy manager
    * @param _minutesPerPeriod Size of period in minutes
    **/
    function EscrowTest(address _node, uint256 _minutesPerPeriod) {
        node = _node;
        secondsPerPeriod = _minutesPerPeriod * 1 minutes;
    }

    /**
    * @notice Return non zero value for node
    **/
    function getLockedTokens(address _owner)
        public constant returns (uint256)
    {
        if (_owner == node) {
            return 1;
        }
        return 0;
    }

    /**
    * @return Number of current period
    **/
    function getCurrentPeriod() public constant returns (uint256) {
        return block.timestamp / secondsPerPeriod;
    }

    /**
    * @notice Set last active period
    **/
    function setLastActivePeriod(uint256 _lastActivePeriod) {
        lastActivePeriod = _lastActivePeriod;
    }

    /**
    * @notice Add downtime period
    **/
    function pushDowntimePeriod(uint256 _startPeriod, uint256 _endPeriod) {
        downtime.push(Downtime(_startPeriod, _endPeriod));
    }

    /**
    * @notice Emulate mint method
    * @param _period Period for minting
    **/
    function mint(uint256 _period) external {
        policyManager.updateReward(node, _period);
    }

    /**
    * @notice Set policy manager address
    **/
    function setPolicyManager(PolicyManager _policyManager) {
        policyManager = _policyManager;
    }

    /**
    * @dev Get info about downtime periods
    **/
    function getDowntimePeriods(address _owner, uint256 _index)
        public constant returns (uint256 startPeriod, uint256 endPeriod)
    {
        var period = downtime[_index];
        startPeriod = period.startPeriod;
        endPeriod = period.endPeriod;
    }

    /**
    * @dev Get size of downtime periods array
    **/
    function getDowntimePeriodsLength(address _owner)
        public constant returns (uint256)
    {
        return downtime.length;
    }

    /**
    * @dev Get last active period
    **/
    function getLastActivePeriod(address _owner)
        public constant returns (uint256)
    {
        return lastActivePeriod;
    }
}
