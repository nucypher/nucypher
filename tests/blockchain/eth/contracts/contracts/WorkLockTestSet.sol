pragma solidity ^0.5.3;


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

    NuCypherToken token;
    uint32 public secondsPerPeriod = 1;
    uint256 public minAllowableLockedTokens;
    uint256 public maxAllowableLockedTokens;
    uint16 public minLockedPeriods;
    mapping (address => StakerInfo) public stakerInfo;

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

    function getCompletedWork(address _staker) public view returns (uint256) {
        return stakerInfo[_staker].completedWork;
    }

    function setWorkMeasurement(address _staker, bool _measureWork) public returns (uint256) {
        stakerInfo[_staker].measureWork = _measureWork;
        return stakerInfo[_staker].completedWork;
    }

    function deposit(address _staker, uint256 _value, uint16 _periods) public {
        stakerInfo[_staker].value = _value;
        stakerInfo[_staker].periods = _periods;
        token.transferFrom(msg.sender, address(this), _value);
    }

    function setCompletedWork(address _staker, uint256 _completedWork) public {
        stakerInfo[_staker].completedWork = _completedWork;
    }

    function burn(uint256 _value) public {
        token.transferFrom(msg.sender, address(this), _value);
    }

}


/**
* @notice Contract for using in WorkLock tests
**/
contract StakingInterfaceMock {}
