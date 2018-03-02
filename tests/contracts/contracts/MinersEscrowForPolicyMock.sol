pragma solidity ^0.4.8;


import "contracts/PolicyManager.sol";


/**
* @notice Contract for using in PolicyManager tests
**/
contract MinersEscrowForPolicyMock {

    struct Downtime {
        uint256 startPeriod;
        uint256 endPeriod;
    }

    PolicyManager public policyManager;
    uint256 public secondsPerPeriod;
    address public node;
    uint256 public lastActivePeriod;
    Downtime[] public downtime;

    /**
    * @param _node Address of node that allow to use policy manager
    * @param _minutesPerPeriod Size of period in minutes
    **/
    function MinersEscrowForPolicyMock(address _node, uint256 _minutesPerPeriod) public {
        node = _node;
        secondsPerPeriod = _minutesPerPeriod * 1 minutes;
    }

    /**
    * @notice Return non zero value for node
    **/
    function getLockedTokens(address _owner)
        public view returns (uint256)
    {
        if (_owner == node) {
            return 1;
        }
        return 0;
    }

    /**
    * @return Number of current period
    **/
    function getCurrentPeriod() public view returns (uint256) {
        return block.timestamp / secondsPerPeriod;
    }

    /**
    * @notice Set last active period
    **/
    function setLastActivePeriod(uint256 _lastActivePeriod) external {
        lastActivePeriod = _lastActivePeriod;
    }

    /**
    * @notice Add downtime period
    **/
    function pushDowntimePeriod(uint256 _startPeriod, uint256 _endPeriod) external {
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
    function setPolicyManager(PolicyManager _policyManager) external {
        policyManager = _policyManager;
    }

    /**
    * @dev Get info about downtime periods
    **/
    function getDowntimePeriods(address, uint256 _index)
        public view returns (uint256 startPeriod, uint256 endPeriod)
    {
        Downtime storage period = downtime[_index];
        startPeriod = period.startPeriod;
        endPeriod = period.endPeriod;
    }

    /**
    * @dev Get size of downtime periods array
    **/
    function getDowntimePeriodsLength(address)
        public view returns (uint256)
    {
        return downtime.length;
    }

    /**
    * @dev Get last active period
    **/
    function getLastActivePeriod(address)
        public view returns (uint256)
    {
        return lastActivePeriod;
    }
}
