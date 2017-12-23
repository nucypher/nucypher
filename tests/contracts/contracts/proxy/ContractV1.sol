pragma solidity ^0.4.18;


import "./ContractInterface.sol";
import "contracts/proxy/Upgradeable.sol";


/**
* @dev Based on from https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/upgradableImplementations/ContractV1.sol
**/
contract ContractV1 is ContractInterface, Upgradeable {

    // The storage layout must remain the same in all the upgraded contracts, although it can be added to.
    // Note that besides the potential mess of unnecessary variables this could create over time, there isn't currently
    // any increase in cost because of this.
    uint public storageValue;
    // Test dynamically sized values // TODO fix bugs
    string public dynamicallySizedValue;
    // Test array values
    uint[] public arrayValues;
    // Test mappings values
    mapping (uint => uint) public mappingValues;
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

    function returnValue() public constant returns (uint) {
        return 10;
    }

    function setStorageValue(uint value) public {
        storageValue = value;
    }
    // We can't use the automatically created getter methods for public vars if
    // we want them to be updatable because we can't specify them in an interface.
    function getStorageValue() public constant returns (uint) {
        return storageValue;
    }

    function setDynamicallySizedValue(string dynamicValue) public {
        dynamicallySizedValue = dynamicValue;
    }
    function getDynamicallySizedValue() public constant returns (string) {
        return dynamicallySizedValue;
    }

    function pushArrayValue(uint value) public {
        arrayValues.push(value);
    }
    function getArrayValue(uint index) public constant returns (uint) {
        return arrayValues[index];
    }
    function getArrayValueLength() public constant returns (uint) {
        return arrayValues.length;
    }

    function setMappingValue(uint index, uint value) public {
        mappingIndices.push(index);
        mappingValues[index] = value;
    }
    function getMappingValue(uint index) public constant returns (uint) {
        return mappingValues[index];
    }

    function getStructureLength1() public constant returns (uint) {
        return arrayStructures.length;
    }
    function pushStructureValue1(uint value) public {
        Structure1 memory structure;
        arrayStructures.push(structure);
        arrayStructures[arrayStructures.length - 1].value = value;
    }
    function getStructureValue1(uint index) public constant returns (uint) {
        return arrayStructures[index].value;
    }
    function getStructureArrayLength1(uint index) public constant returns (uint) {
        return arrayStructures[index].arrayValues.length;
    }
    function pushStructureArrayValue1(uint index, uint value) public {
        arrayStructures[index].arrayValues.push(value);
    }
    function getStructureArrayValue1(uint index, uint arrayIndex) public constant returns (uint) {
        return arrayStructures[index].arrayValues[arrayIndex];
    }

    function getStructureLength2() public constant returns (uint) {
        return mappingStructuresLength;
    }
    function pushStructureValue2(uint value) public {
        mappingStructuresLength++;
        Structure2 memory structure;
        mappingStructures[mappingStructuresLength - 1] = structure;
        mappingStructures[mappingStructuresLength - 1].value = value;
    }
    function getStructureValue2(uint index) public constant returns (uint) {
        return mappingStructures[index].value;
    }
    function getStructureArrayLength2(uint index) public constant returns (uint) {
        return mappingStructures[index].arrayValues.length;
    }
    function pushStructureArrayValue2(uint index, uint value) public {
        mappingStructures[index].arrayValues.push(value);
    }
    function getStructureArrayValue2(uint index, uint arrayIndex) public constant returns (uint) {
        return mappingStructures[index].arrayValues[arrayIndex];
    }

    function verifyState(address testTarget) public {
        require(uint(delegateGet(testTarget, "storageValue()")) == storageValue);
        //TODO uncomment after fixing return size
//        require(address(delegateGet(testTarget, "dynamicallySizedValue()")) == owner);

        require(uint(delegateGet(testTarget, "getArrayValueLength()")) == arrayValues.length);
        for (uint i = 0; i < arrayValues.length; i++) {
            require(uint(delegateGet(testTarget, "getArrayValue(uint256)", bytes32(i))) ==
                arrayValues[i]);
        }
        for (i = 0; i < mappingIndices.length; i++) {
            var index = mappingIndices[i];
            require(uint(delegateGet(testTarget, "getMappingValue(uint256)", bytes32(index))) ==
                mappingValues[index]);
        }

        require(uint(delegateGet(testTarget, "getStructureLength1()")) == arrayStructures.length);
        for (i = 0; i < arrayStructures.length; i++) {
            require(uint(delegateGet(testTarget, "getStructureValue1(uint256)", bytes32(i))) ==
                arrayStructures[i].value);
            require(uint(delegateGet(testTarget, "getStructureArrayLength1(uint256)", bytes32(i))) ==
                arrayStructures[i].arrayValues.length);
            for (uint j = 0; j < arrayStructures[i].arrayValues.length; j++) {
                require(uint(delegateGet(
                        testTarget, "getStructureArrayValue1(uint256,uint256)", bytes32(i), bytes32(j))) ==
                    arrayStructures[i].arrayValues[j]);
            }
        }

        require(uint(delegateGet(testTarget, "getStructureLength2()")) == mappingStructuresLength);
        for (i = 0; i < mappingStructuresLength; i++) {
            require(uint(delegateGet(testTarget, "getStructureValue2(uint256)", bytes32(i))) ==
                mappingStructures[i].value);
            require(uint(delegateGet(testTarget, "getStructureArrayLength2(uint256)", bytes32(i))) ==
                mappingStructures[i].arrayValues.length);
            for (j = 0; j < mappingStructures[i].arrayValues.length; j++) {
                require(uint(delegateGet(
                        testTarget, "getStructureArrayValue2(uint256,uint256)", bytes32(i), bytes32(j))) ==
                    mappingStructures[i].arrayValues[j]);
            }
        }
    }

}
