pragma solidity ^0.4.18;


import "./ContractInterface.sol";
import "contracts/proxy/Upgradeable.sol";


contract ContractV2Bad is ContractInterface, Upgradeable {

    uint32 public storageValue;
    uint[] public updatedDynamicallySizedValue;
    //TODO delete after fixing return size
    uint public storageValueToCheck;

    function returnValue() public constant returns (uint) {}

    function setStorageValue(uint value) public {}

    function getStorageValue() public constant returns (uint) {}

    function setDynamicallySizedValue(string dynamicValue) public {}

    function getDynamicallySizedValue() public constant returns (string) {}

    function setDynamicallySizedValue(uint[] _updatedDynamicallySizedValue) public {}

    function getUpdatedDynamicallySizedValue() public constant returns (uint[]) {}

    function verifyState(address testTarget) public {}

}
