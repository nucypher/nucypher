pragma solidity ^0.4.18;


import "./ContractInterface.sol";
import "proxy/Upgradeable.sol";


/**
* @dev Based on from https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/upgradableImplementations/ContractV1.sol
**/
contract ContractV1 is ContractInterface, Upgradeable {

    event EventV1(uint256 value);

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

    constructor(uint _storageValue) public {
        storageValue = _storageValue;
    }

    function returnValue() public pure returns (uint) {
        return 10;
    }

    function setStorageValue(uint _value) public {
        storageValue = _value;
    }
    // We can't use the automatically created getter methods for public vars if
    // we want them to be updatable because we can't specify them in an interface.
    function getStorageValue() public view returns (uint) {
        return storageValue;
    }

    function setDynamicallySizedValue(string _dynamicValue) public {
        dynamicallySizedValue = _dynamicValue;
    }
    function getDynamicallySizedValue() public view returns (string) {
        return dynamicallySizedValue;
    }

    function pushArrayValue(uint _value) public {
        arrayValues.push(_value);
    }
    function getArrayValue(uint _index) public view returns (uint) {
        return arrayValues[_index];
    }
    function getArrayValueLength() public view returns (uint) {
        return arrayValues.length;
    }

    function setMappingValue(uint _index, uint _value) public {
        mappingIndices.push(_index);
        mappingValues[_index] = _value;
    }
    function getMappingValue(uint _index) public view returns (uint) {
        return mappingValues[_index];
    }

    function getStructureLength1() public view returns (uint) {
        return arrayStructures.length;
    }
    function pushStructureValue1(uint _value) public {
        Structure1 memory structure;
        arrayStructures.push(structure);
        arrayStructures[arrayStructures.length - 1].value = _value;
    }
    function getStructureValue1(uint _index) public view returns (uint) {
        return arrayStructures[_index].value;
    }
    function getStructureArrayLength1(uint _index) public view returns (uint) {
        return arrayStructures[_index].arrayValues.length;
    }
    function pushStructureArrayValue1(uint _index, uint _value) public {
        arrayStructures[_index].arrayValues.push(_value);
    }
    function getStructureArrayValue1(uint _index, uint _arrayIndex) public view returns (uint) {
        return arrayStructures[_index].arrayValues[_arrayIndex];
    }

    function getStructureLength2() public view returns (uint) {
        return mappingStructuresLength;
    }
    function pushStructureValue2(uint _value) public {
        mappingStructuresLength++;
        Structure2 memory structure;
        mappingStructures[mappingStructuresLength - 1] = structure;
        mappingStructures[mappingStructuresLength - 1].value = _value;
    }
    function getStructureValue2(uint _index) public view returns (uint) {
        return mappingStructures[_index].value;
    }
    function getStructureArrayLength2(uint _index) public view returns (uint) {
        return mappingStructures[_index].arrayValues.length;
    }
    function pushStructureArrayValue2(uint _index, uint _value) public {
        mappingStructures[_index].arrayValues.push(_value);
    }
    function getStructureArrayValue2(uint _index, uint _arrayIndex) public view returns (uint) {
        return mappingStructures[_index].arrayValues[_arrayIndex];
    }

    function verifyState(address _testTarget) public onlyOwner {
        require(uint(delegateGet(_testTarget, "storageValue()")) == storageValue);
        //TODO uncomment after fixing return size
//        require(address(delegateGet(_testTarget, "dynamicallySizedValue()")) == owner);

        require(uint(delegateGet(_testTarget, "getArrayValueLength()")) == arrayValues.length);
        for (uint i = 0; i < arrayValues.length; i++) {
            require(uint(delegateGet(_testTarget, "getArrayValue(uint256)", bytes32(i))) ==
                arrayValues[i]);
        }
        for (i = 0; i < mappingIndices.length; i++) {
            uint256 index = mappingIndices[i];
            require(uint(delegateGet(_testTarget, "getMappingValue(uint256)", bytes32(index))) ==
                mappingValues[index]);
        }

        require(uint(delegateGet(_testTarget, "getStructureLength1()")) == arrayStructures.length);
        for (i = 0; i < arrayStructures.length; i++) {
            require(uint(delegateGet(_testTarget, "getStructureValue1(uint256)", bytes32(i))) ==
                arrayStructures[i].value);
            require(uint(delegateGet(_testTarget, "getStructureArrayLength1(uint256)", bytes32(i))) ==
                arrayStructures[i].arrayValues.length);
            for (uint j = 0; j < arrayStructures[i].arrayValues.length; j++) {
                require(uint(delegateGet(
                        _testTarget, "getStructureArrayValue1(uint256,uint256)", bytes32(i), bytes32(j))) ==
                    arrayStructures[i].arrayValues[j]);
            }
        }

        require(uint(delegateGet(_testTarget, "getStructureLength2()")) == mappingStructuresLength);
        for (i = 0; i < mappingStructuresLength; i++) {
            require(uint(delegateGet(_testTarget, "getStructureValue2(uint256)", bytes32(i))) ==
                mappingStructures[i].value);
            require(uint(delegateGet(_testTarget, "getStructureArrayLength2(uint256)", bytes32(i))) ==
                mappingStructures[i].arrayValues.length);
            for (j = 0; j < mappingStructures[i].arrayValues.length; j++) {
                require(uint(delegateGet(
                        _testTarget, "getStructureArrayValue2(uint256,uint256)", bytes32(i), bytes32(j))) ==
                    mappingStructures[i].arrayValues[j]);
            }
        }
    }

    function finishUpgrade(address _target) public onlyOwner {
        storageValue = ContractV1(_target).storageValue();
    }

    function createEvent(uint256 _value) public {
        emit EventV1(_value);
    }
}
