pragma solidity ^0.5.3;


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
        uint16 _minLockedPeriods,
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
            _minLockedPeriods,
            _minAllowableLockedTokens,
            _maxAllowableLockedTokens
        )
    {
    }

    function getSubStakeInfo(address, uint256) public view returns (uint16, uint16, uint16, uint256)
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
        uint16 _minLockedPeriods,
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
            _minLockedPeriods,
            _minAllowableLockedTokens,
            _maxAllowableLockedTokens
        )
    {
        valueToCheck = _valueToCheck;
    }

    function setValueToCheck(uint256 _valueToCheck) public {
        valueToCheck = _valueToCheck;
    }

    function verifyState(address _testTarget) public {
        super.verifyState(_testTarget);
        require(delegateGet(_testTarget, "valueToCheck()") == valueToCheck);
    }

    function finishUpgrade(address _target) public onlyWhileUpgrading {
        MinersEscrowV2Mock escrow = MinersEscrowV2Mock(_target);
        valueToCheck = escrow.valueToCheck();
        emit UpgradeFinished(_target, msg.sender);
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


/**
* @notice Contract for testing miners escrow contract
**/
contract MiningAdjudicatorForMinersEscrowMock {

    MinersEscrow public escrow;

    constructor(MinersEscrow _escrow) public {
        escrow = _escrow;
    }

    function slashMiner(
        address _miner,
        uint256 _penalty,
        address _investigator,
        uint256 _reward
    )
        public
    {
        escrow.slashMiner(_miner, _penalty, _investigator, _reward);
    }
}

/**
* @notice Intermediary contract for testing worker
**/
contract Intermediary {

    NuCypherToken token;
    MinersEscrow escrow;

    constructor(NuCypherToken _token, MinersEscrow _escrow) public {
        token = _token;
        escrow = _escrow;
    }

    function setWorker(address _worker) public {
        escrow.setWorker(_worker);
    }

    function deposit(uint256 _value, uint16 _periods) public {
        token.approve(address(escrow), _value);
        escrow.deposit(_value, _periods);
    }

    function confirmActivity() public {
        escrow.confirmActivity();
    }

}
