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
    string public dynamicallySizedValue;
    uint[] public arrayValues;
    mapping (uint => uint) public mappingValues;
    uint[] public mappingIndices;

    struct Structure {
        uint value;
        uint[] arrayValues;
    }
    Structure[] public structures;

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

    function getStructureLength() public constant returns (uint) {
        return structures.length;
    }

    function pushStructureValue(uint value) public {
        Structure memory structure;
        structures.push(structure);
        structures[structures.length - 1].value = value;
    }

    function getStructureValue(uint index) public constant returns (uint) {
        return structures[index].value;
    }

    function getStructureArrayLength(uint index) public constant returns (uint) {
        return structures[index].arrayValues.length;
    }

    function pushStructureArrayValue(uint index, uint value) public {
        structures[index].arrayValues.push(value);
    }

    function getStructureArrayValue(uint index, uint arrayIndex) public constant returns (uint) {
        return structures[index].arrayValues[arrayIndex];
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

        require(uint(delegateGet(testTarget, "getStructureLength()")) == structures.length);
        for (i = 0; i < structures.length; i++) {
            require(uint(delegateGet(testTarget, "getStructureValue(uint256)", bytes32(i))) ==
                structures[i].value);
            require(uint(delegateGet(testTarget, "getStructureArrayLength(uint256)", bytes32(i))) ==
                structures[i].arrayValues.length);
            for (uint j = 0; j < structures[i].arrayValues.length; j++) {
                require(uint(delegateGet(
                        testTarget, "getStructureArrayValue(uint256,uint256)", bytes32(i), bytes32(j))) ==
                    structures[i].arrayValues[j]);
            }
        }
    }

}
