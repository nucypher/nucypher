pragma solidity ^0.4.18;


import "contracts/PolicyManager.sol";
import "contracts/MinersEscrow.sol";


/**
* @notice Contract for using in Government tests
**/
contract PolicyManagerV2Mock is PolicyManager {

    uint256 public valueToCheck;

    constructor(MinersEscrow _escrow) public PolicyManager(_escrow) {
    }

    function setValueToCheck(uint256 _valueToCheck) public {
        valueToCheck = _valueToCheck;
    }

    function verifyState(address _testTarget) public onlyOwner {
        super.verifyState(_testTarget);
        require(uint256(delegateGet(_testTarget, "valueToCheck()")) == valueToCheck);
    }
}
