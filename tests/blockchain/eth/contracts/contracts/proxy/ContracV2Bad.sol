pragma solidity ^0.4.18;


import "./ContractInterface.sol";
import "proxy/Upgradeable.sol";


contract ContractV2Bad is ContractInterface, Upgradeable {

    event EventV1(uint256 value);

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

    function returnValue() public pure returns (uint) {}

    function setStorageValue(uint) public {}
    function getStorageValue() public view returns (uint) {
        return storageValue;
    }

    function setDynamicallySizedValue(string) public {}
    function getDynamicallySizedValue() public view returns (string) {}

    function pushArrayValue(uint) public {}
    function getArrayValue(uint _index) public view returns (uint) {
        return arrayValues[_index];
    }
    function getArrayValueLength() public view returns (uint) {
        return arrayValues.length;
    }

    function setMappingValue(uint, uint) public {}
    function getMappingValue(uint _index) public view returns (uint) {
        return mappingValues[_index];
    }

    function getStructureLength1() public view returns (uint) {
        return arrayStructures.length;
    }
    function pushStructureValue1(uint) public {}
    function getStructureValue1(uint _index) public view returns (uint) {
        return arrayStructures[_index].value;
    }
    function getStructureArrayLength1(uint _index) public view returns (uint) {
        return arrayStructures[_index].arrayValues.length;
    }
    function pushStructureArrayValue1(uint, uint) public {}
    function getStructureArrayValue1(uint _index, uint _arrayIndex) public view returns (uint) {
        return arrayStructures[_index].arrayValues[_arrayIndex];
    }

    function getStructureLength2() public view returns (uint) {
        return mappingStructuresLength;
    }
    function pushStructureValue2(uint) public {}
    function getStructureValue2(uint _index) public view returns (uint) {
        return mappingStructures[_index].value;
    }
    function getStructureArrayLength2(uint _index) public view returns (uint) {
        return mappingStructures[_index].arrayValues.length;
    }
    function pushStructureArrayValue2(uint, uint) public {}
    function getStructureArrayValue2(uint _index, uint _arrayIndex) public view returns (uint) {
        return mappingStructures[_index].arrayValues[_arrayIndex];
    }

    function verifyState(address) public {}
    function finishUpgrade(address) public {}

}
