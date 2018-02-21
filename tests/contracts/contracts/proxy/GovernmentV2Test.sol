pragma solidity ^0.4.18;


import "contracts/proxy/Government.sol";


/**
* @notice Contract for using in Government tests
**/
contract GovernmentV2Test is Government {

    uint256 public valueToCheck;

    function GovernmentV2Test(
        Dispatcher _escrow,
        Dispatcher _policyManager,
        uint256 _votingDurationHours)
        Government(_escrow, _policyManager, _votingDurationHours)
    {
    }

    function setValueToCheck(uint256 _valueToCheck) public {
        valueToCheck = _valueToCheck;
    }

    function verifyState(address _testTarget) public constant {
        super.verifyState(_testTarget);
        require(uint256(delegateGet(_testTarget, "valueToCheck()")) == valueToCheck);
    }
}
