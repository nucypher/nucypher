pragma solidity ^0.4.18;


import "./ContractV2.sol";


contract ContractV3 is ContractV2 {

    uint public anotherStorageValue;

    function setAnotherStorageValue(uint value) public {
        anotherStorageValue = value * 2;
    }

    function getAnotherStorageValue() public constant returns (uint) {
        return storageValue;
    }

    function verifyState(address testTarget) public {
        super.verifyState(testTarget);
        require(uint(delegateGet(testTarget, "anotherStorageValue()")) == anotherStorageValue);
    }
}
