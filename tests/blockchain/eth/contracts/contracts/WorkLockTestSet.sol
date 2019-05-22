pragma solidity ^0.5.3;


import "contracts/NuCypherToken.sol";


/**
* @notice Contract for using in WorkLock tests
**/
contract MinersEscrowForWorkLockMock {

    struct MinerInfo {
        uint256 value;
        bool measureWork;
        uint256 workDone;
        uint16 periods;
    }

    NuCypherToken token;
    uint32 public secondsPerPeriod = 1;
    uint256 public minAllowableLockedTokens;
    uint256 public maxAllowableLockedTokens;
    uint16 public minLockedPeriods;
    mapping (address => MinerInfo) public minerInfo;

    constructor(
        NuCypherToken _token,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens,
        uint16 _minLockedPeriods
    )
        public
    {
        token = _token;
        minAllowableLockedTokens = _minAllowableLockedTokens;
        maxAllowableLockedTokens = _maxAllowableLockedTokens;
        minLockedPeriods = _minLockedPeriods;
    }

    function getWorkDone(address _miner) public view returns (uint256) {
        return minerInfo[_miner].workDone;
    }

    function setWorkMeasurement(address _miner, bool _measureWork) public returns (uint256) {
        minerInfo[_miner].measureWork = _measureWork;
        return minerInfo[_miner].workDone;
    }

    function deposit(address _miner, uint256 _value, uint16 _periods) public {
        minerInfo[_miner].value = _value;
        minerInfo[_miner].periods = _periods;
        token.transferFrom(msg.sender, address(this), _value);
    }

    function setWorkDone(address _miner, uint256 _workDone) public {
        minerInfo[_miner].workDone = _workDone;
    }

}
