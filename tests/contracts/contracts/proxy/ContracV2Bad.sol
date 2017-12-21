pragma solidity ^0.4.18;


import "./ContractInterface.sol";
import "contracts/proxy/Upgradeable.sol";


contract ContractV2Bad is ContractInterface, Upgradeable {

    uint32 public storageValue;
    string public dynamicallySizedValue;
    uint[] arrayValues;
    mapping (uint => uint) mappingValues;
    uint[] public mappingIndices;

    function returnValue() public constant returns (uint) {}

    function setStorageValue(uint value) public {}
    function getStorageValue() public constant returns (uint) {
        return storageValue;
    }

    function setDynamicallySizedValue(string dynamicValue) public {}
    function getDynamicallySizedValue() public constant returns (string) {}

    function pushArrayValue(uint value) public {}
    function getArrayValue(uint index) public constant returns (uint) {
        return arrayValues[index];
    }
    function getArrayValueLength() public constant returns (uint) {
        return arrayValues.length;
    }

    function setMappingValue(uint index, uint value) public {}
    function getMappingValue(uint index) public constant returns (uint) {
        return mappingValues[index];
    }

    function verifyState(address testTarget) public {}

}
