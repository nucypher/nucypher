pragma solidity ^0.4.24;


import "contracts/MinersEscrow.sol";
import "contracts/NuCypherToken.sol";


/**
* @notice Upgrade to this contract must lead to fail
**/
contract MinersEscrowBad is MinersEscrow {

    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint16 _rewardedPeriods,
        uint16 _minReleasePeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens
    )
        public
        MinersEscrow(
            _token,
            _hoursPerPeriod,
            _miningCoefficient,
            _lockedPeriodsCoefficient,
            _rewardedPeriods,
            _minReleasePeriods,
            _minAllowableLockedTokens,
            _maxAllowableLockedTokens
        )
    {
    }

    function getStakeInfo(address, uint256) public view returns (uint16, uint16, uint16, uint256)
    {
    }

}


/**
* @notice Contract for testing upgrading the MinersEscrow contract
**/
contract MinersEscrowV2Mock is MinersEscrow {

    uint256 public valueToCheck;

    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint16 _rewardedPeriods,
        uint16 _minReleasePeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens,
        uint256 _valueToCheck
    )
        public
        MinersEscrow(
            _token,
            _hoursPerPeriod,
            _miningCoefficient,
            _lockedPeriodsCoefficient,
            _rewardedPeriods,
            _minReleasePeriods,
            _minAllowableLockedTokens,
            _maxAllowableLockedTokens
        )
    {
        valueToCheck = _valueToCheck;
    }

    function setValueToCheck(uint256 _valueToCheck) public {
        valueToCheck = _valueToCheck;
    }

    function verifyState(address _testTarget) public onlyOwner {
        super.verifyState(_testTarget);
        require(uint256(delegateGet(_testTarget, "valueToCheck()")) == valueToCheck);
    }

    function finishUpgrade(address _target) public onlyOwner {
        MinersEscrowV2Mock escrow = MinersEscrowV2Mock(_target);
        valueToCheck = escrow.valueToCheck();
    }
}


/**
* @notice Contract for testing miners escrow contract
**/
contract PolicyManagerForMinersEscrowMock {

    MinersEscrow public escrow;
    mapping (address => uint16[]) public nodes;

    constructor(address, MinersEscrow _escrow) public {
        escrow = _escrow;
    }

    function register(address _node, uint16 _period) external {
        nodes[_node].push(_period);
    }

    /**
    * @notice Update node info
    **/
    function updateReward(address _node, uint16 _period) external {
        nodes[_node].push(_period);
    }

    /**
    * @notice Get length of array
    **/
    function getPeriodsLength(address _node) public view returns (uint256) {
        return nodes[_node].length;
    }

    /**
    * @notice Get period info
    **/
    function getPeriod(address _node, uint256 _index) public view returns (uint16) {
        return nodes[_node][_index];
    }

}