pragma solidity ^0.4.18;


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
    mapping(address => bool) public nodes;
    uint256 public lastActivePeriod;
    Downtime[] public downtime;

    /**
    * @param _nodes Addresses of nodes that allow to use policy manager
    * @param _minutesPerPeriod Size of period in minutes
    **/
    constructor(address[] _nodes, uint256 _minutesPerPeriod) public {
        for (uint256 i = 0; i < _nodes.length; i++) {
            nodes[_nodes[i]] = true;
        }
        secondsPerPeriod = _minutesPerPeriod * 1 minutes;
    }

    /**
    * @notice Return non zero value for node
    **/
    function getLockedTokens(address _owner)
        public view returns (uint256)
    {
        if (nodes[_owner]) {
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

    function getMinerInfo(MinersEscrow.MinerInfoField _field, address, uint256 _index)
        public view returns (bytes32)
    {
        if (_field == MinersEscrow.MinerInfoField.LastActivePeriod) {
            return bytes32(lastActivePeriod);
        } else if (_field == MinersEscrow.MinerInfoField.DowntimeLength) {
            return bytes32(downtime.length);
        } else if (_field == MinersEscrow.MinerInfoField.DowntimeStartPeriod) {
            return bytes32(downtime[_index].startPeriod);
        } else if (_field == MinersEscrow.MinerInfoField.DowntimeEndPeriod) {
            return bytes32(downtime[_index].endPeriod);
        }
    }
}
