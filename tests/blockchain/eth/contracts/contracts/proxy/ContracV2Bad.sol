pragma solidity ^0.5.3;


import "./ContractInterface.sol";
import "contracts/proxy/Upgradeable.sol";


contract ContractV2Bad is ContractInterface, Upgradeable {

    event EventV1(uint256 value);
    // TODO can't catch such a violation
//    uint128 public storageValue;
    uint256 public storageValue;
    uint128 public fakeValue;
    string public dynamicallySizedValue;
    uint256[] arrayValues;
    mapping (uint256 => uint256) mappingValues;
    uint256[] public mappingIndices;

    // Test struct which used in arrays
    struct Structure1 {
        uint256 value;
        uint256[] arrayValues;
    }
    Structure1[] public arrayStructures;

    // Test struct which used in mappings
    struct Structure2 {
        uint256 value;
        uint256[] arrayValues;
    }
    mapping (uint256 => Structure2) public mappingStructures;
    uint256 public mappingStructuresLength;

    function returnValue() public pure returns (uint256) {}

    function setStorageValue(uint256) public {}
    function getStorageValue() public view returns (uint256) {
        return storageValue;
    }

    function setDynamicallySizedValue(string memory) public {}
    function getDynamicallySizedValue() public view returns (string memory) {}

    function pushArrayValue(uint256) public {}
    function getArrayValue(uint256 _index) public view returns (uint256) {
        return arrayValues[_index];
    }
    function getArrayValueLength() public view returns (uint256) {
        return arrayValues.length;
    }

    function setMappingValue(uint256, uint256) public {}
    function getMappingValue(uint256 _index) public view returns (uint256) {
        return mappingValues[_index];
    }

    function getStructureLength1() public view returns (uint256) {
        return arrayStructures.length;
    }
    function pushStructureValue1(uint256) public {}
    function getStructureValue1(uint256 _index) public view returns (uint256) {
        return arrayStructures[_index].value;
    }
    function getStructureArrayLength1(uint256 _index) public view returns (uint256) {
        return arrayStructures[_index].arrayValues.length;
    }
    function pushStructureArrayValue1(uint256, uint256) public {}
    function getStructureArrayValue1(uint256 _index, uint256 _arrayIndex) public view returns (uint256) {
        return arrayStructures[_index].arrayValues[_arrayIndex];
    }

    function getStructureLength2() public view returns (uint256) {
        return mappingStructuresLength;
    }
    function pushStructureValue2(uint256) public {}
    function getStructureValue2(uint256 _index) public view returns (uint256) {
        return mappingStructures[_index].value;
    }
    function getStructureArrayLength2(uint256 _index) public view returns (uint256) {
        return mappingStructures[_index].arrayValues.length;
    }
    function pushStructureArrayValue2(uint256, uint256) public {}
    function getStructureArrayValue2(uint256 _index, uint256 _arrayIndex) public view returns (uint256) {
        return mappingStructures[_index].arrayValues[_arrayIndex];
    }

    function verifyState(address) public {}
    function finishUpgrade(address) public {}

}
