pragma solidity ^0.4.18;


import "contracts/MinersEscrow.sol";
import "contracts/NuCypherKMSToken.sol";


/**
* @notice Contract for using in Government tests
**/
contract MinersEscrowV2Mock is MinersEscrow {

    uint256 public valueToCheck;

    constructor(
        NuCypherKMSToken _token,
        uint256 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint256 _awardedPeriods,
        uint256 _minReleasePeriods,
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
            _awardedPeriods,
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
