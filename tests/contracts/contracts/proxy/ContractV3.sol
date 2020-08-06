// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


import "./ContractV2.sol";


contract ContractV3 is ContractV2 {

    uint256 public anotherStorageValue;

    constructor(uint256 _storageValueToCheck)
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
