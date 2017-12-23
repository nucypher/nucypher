pragma solidity ^0.4.18;


import "./ContractInterface.sol";
import "contracts/proxy/Upgradeable.sol";


contract ContractV2Bad is ContractInterface, Upgradeable {

    uint32 public storageValue;
    string public dynamicallySizedValue;
    uint[] arrayValues;
    mapping (uint => uint) mappingValues;
    uint[] public mappingIndices;

    // Test struct which used in arrays
    struct Structure1 {
        uint value;
        uint[] arrayValues;
    }
    Structure1[] public arrayStructures;

    // Test struct which used in mappings
    struct Structure2 {
        uint value;
        uint[] arrayValues;
    }
    mapping (uint => Structure2) public mappingStructures;
    uint public mappingStructuresLength;

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

    function getStructureLength1() public constant returns (uint) {
        return arrayStructures.length;
    }
    function pushStructureValue1(uint value) public {}
    function getStructureValue1(uint index) public constant returns (uint) {
        return arrayStructures[index].value;
    }
    function getStructureArrayLength1(uint index) public constant returns (uint) {
        return arrayStructures[index].arrayValues.length;
    }
    function pushStructureArrayValue1(uint index, uint value) public {}
    function getStructureArrayValue1(uint index, uint arrayIndex) public constant returns (uint) {
        return arrayStructures[index].arrayValues[arrayIndex];
    }

    function getStructureLength2() public constant returns (uint) {
        return mappingStructuresLength;
    }
    function pushStructureValue2(uint value) public {}
    function getStructureValue2(uint index) public constant returns (uint) {
        return mappingStructures[index].value;
    }
    function getStructureArrayLength2(uint index) public constant returns (uint) {
        return mappingStructures[index].arrayValues.length;
    }
    function pushStructureArrayValue2(uint index, uint value) public {}
    function getStructureArrayValue2(uint index, uint arrayIndex) public constant returns (uint) {
        return mappingStructures[index].arrayValues[arrayIndex];
    }



    function verifyState(address testTarget) public {}

}
