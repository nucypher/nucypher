pragma solidity ^0.4.18;


import "./ContractV2.sol";


contract ContractV3 is ContractV2 {

    uint public anotherStorageValue;

    function ContractV3(uint _storageValueToCheck)
        public
        ContractV2(_storageValueToCheck)
    {
    }

    function setAnotherStorageValue(uint _value) public {
        anotherStorageValue = _value * 2;
    }

    function verifyState(address _testTarget) public onlyOwner {
        super.verifyState(_testTarget);
        require(uint(delegateGet(_testTarget, "anotherStorageValue()")) == anotherStorageValue);
    }
}
