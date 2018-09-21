pragma solidity ^0.4.24;


import "contracts/Issuer.sol";
import "contracts/NuCypherToken.sol";
import "contracts/proxy/Upgradeable.sol";


/**
* @dev Contract for testing internal methods in the Issuer contract
**/
contract IssuerMock is Issuer {

    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint16 _rewardedPeriods
    )
        public
        Issuer(
            _token,
            _hoursPerPeriod,
            _miningCoefficient,
            _lockedPeriodsCoefficient,
            _rewardedPeriods
        )
    {
    }

    function testMint(
        uint16 _period,
        uint256 _lockedValue,
        uint256 _totalLockedValue,
        uint16 _allLockedPeriods
    )
        public returns (uint256 amount)
    {
        amount = mint(
            _period,
            _lockedValue,
            _totalLockedValue,
            _allLockedPeriods);
        token.transfer(msg.sender, amount);
    }

}


/**
* @notice Upgrade to this contract must lead to fail
**/
contract IssuerBad is Upgradeable {

    address public token;
    uint256 public miningCoefficient;
    uint256 public lockedPeriodsCoefficient;
    uint32 public secondsPerPeriod;
    uint16 public rewardedPeriods;

    uint16 public lastMintedPeriod;
//    uint256 public currentSupply1;
    uint256 public currentSupply2;

    function verifyState(address) public {}
    function finishUpgrade(address) public {}

}


/**
* @notice Contract for testing upgrading the Issuer contract
**/
contract IssuerV2Mock is Issuer {

    uint256 public valueToCheck;

    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint16 _rewardedPeriods
    )
        public
        Issuer(
            _token,
            _hoursPerPeriod,
            _miningCoefficient,
            _lockedPeriodsCoefficient,
            _rewardedPeriods
        )
    {
    }

    function setValueToCheck(uint256 _valueToCheck) public {
        valueToCheck = _valueToCheck;
    }

    function verifyState(address _testTarget) public onlyOwner {
        super.verifyState(_testTarget);
        require(uint256(delegateGet(_testTarget, "valueToCheck()")) == valueToCheck);
    }
}

