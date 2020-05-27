pragma solidity ^0.6.1;


import "./ContractV2.sol";


contract ContractV3 is ContractV2 {

    uint256 public anotherStorageValue;

    constructor(uint256 _storageValueToCheck)
        public
        ContractV2(_storageValueToCheck)
    {
    }

    function setAnotherStorageValue(uint256 _value) public {
        anotherStorageValue = _value;
    }

    function verifyState(address _testTarget) public override {
        super.verifyState(_testTarget);
        require(delegateGet(_testTarget, this.anotherStorageValue.selector) == anotherStorageValue);
    }
}
