pragma solidity ^0.4.18;


import "proxy/Government.sol";


/**
* @notice Contract for using in Government tests
**/
contract GovernmentV2Mock is Government {

    uint256 public valueToCheck;

    constructor(
        Dispatcher _escrow,
        Dispatcher _policyManager,
        uint256 _votingDurationHours
    )
        public
        Government(_escrow, _policyManager, _votingDurationHours)
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
