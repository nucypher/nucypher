pragma solidity ^0.4.23;


import "contracts/PolicyManager.sol";
import "contracts/MinersEscrow.sol";


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
    uint256 public lastActivePeriod;
    Downtime[] public downtime;

    /**
    * @param _hoursPerPeriod Size of period in hours
    **/
    constructor(uint256 _hoursPerPeriod) public {
        secondsPerPeriod = _hoursPerPeriod * 1 hours;
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
    * @param _startPeriod Start period for minting
    * @param _numberOfPeriods Number periods for minting
    **/
    function mint(uint256 _startPeriod, uint256 _numberOfPeriods) external {
        for (uint256 i = 0; i < _numberOfPeriods; i++) {
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
    function getDowntimeLength(address) public view returns (uint256) {
        return downtime.length;
    }

    /**
    * @notice Emulate getDowntime
    **/
    function getDowntime(address, uint256 _index)
        public view returns (uint256 startPeriod, uint256 endPeriod)
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
