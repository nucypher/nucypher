pragma solidity ^0.5.3;


import "./ContractInterface.sol";
import "contracts/proxy/Upgradeable.sol";


/**
* @dev Based on from https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/upgradableImplementations/ContractV1.sol
**/
contract ContractV1 is ContractInterface, Upgradeable {

    event EventV1(uint256 value);

    // The storage layout must remain the same in all the upgraded contracts, although it can be added to.
    // Note that besides the potential mess of unnecessary variables this could create over time, there isn't currently
    // any increase in cost because of this.
    uint256 public storageValue;
    // Test dynamically sized values
    string public dynamicallySizedValue;
    // Test array values
    uint256[] public arrayValues;
    // Test mappings values
    mapping (uint256 => uint256) public mappingValues;
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

    constructor(uint256 _storageValue) public {
        storageValue = _storageValue;
    }

    function returnValue() public pure returns (uint256) {
        return 10;
    }

    function setStorageValue(uint256 _value) public {
        storageValue = _value;
    }
    // We can't use the automatically created getter methods for public vars if
    // we want them to be updatable because we can't specify them in an interface.
    function getStorageValue() public view returns (uint256) {
        return storageValue;
    }

    function setDynamicallySizedValue(string memory _dynamicValue) public {
        dynamicallySizedValue = _dynamicValue;
    }
    function getDynamicallySizedValue() public view returns (string memory) {
        return dynamicallySizedValue;
    }

    function pushArrayValue(uint256 _value) public {
        arrayValues.push(_value);
    }
    function getArrayValue(uint256 _index) public view returns (uint256) {
        return arrayValues[_index];
    }
    function getArrayValueLength() public view returns (uint256) {
        return arrayValues.length;
    }

    function setMappingValue(uint256 _index, uint256 _value) public {
        mappingIndices.push(_index);
        mappingValues[_index] = _value;
    }
    function getMappingValue(uint256 _index) public view returns (uint256) {
        return mappingValues[_index];
    }

    function getStructureLength1() public view returns (uint256) {
        return arrayStructures.length;
    }
    function pushStructureValue1(uint256 _value) public {
        Structure1 memory structure;
        arrayStructures.push(structure);
        arrayStructures[arrayStructures.length - 1].value = _value;
    }
    function getStructureValue1(uint256 _index) public view returns (uint256) {
        return arrayStructures[_index].value;
    }
    function getStructureArrayLength1(uint256 _index) public view returns (uint256) {
        return arrayStructures[_index].arrayValues.length;
    }
    function pushStructureArrayValue1(uint256 _index, uint256 _value) public {
        arrayStructures[_index].arrayValues.push(_value);
    }
    function getStructureArrayValue1(uint256 _index, uint256 _arrayIndex) public view returns (uint256) {
        return arrayStructures[_index].arrayValues[_arrayIndex];
    }

    function getStructureLength2() public view returns (uint256) {
        return mappingStructuresLength;
    }
    function pushStructureValue2(uint256 _value) public {
        mappingStructuresLength++;
        Structure2 memory structure;
        mappingStructures[mappingStructuresLength - 1] = structure;
        mappingStructures[mappingStructuresLength - 1].value = _value;
    }
    function getStructureValue2(uint256 _index) public view returns (uint256) {
        return mappingStructures[_index].value;
    }
    function getStructureArrayLength2(uint256 _index) public view returns (uint256) {
        return mappingStructures[_index].arrayValues.length;
    }
    function pushStructureArrayValue2(uint256 _index, uint256 _value) public {
        mappingStructures[_index].arrayValues.push(_value);
    }
    function getStructureArrayValue2(uint256 _index, uint256 _arrayIndex) public view returns (uint256) {
        return mappingStructures[_index].arrayValues[_arrayIndex];
    }

    function verifyState(address _testTarget) public {
        super.verifyState(_testTarget);
        require(delegateGet(_testTarget, "storageValue()") == storageValue);
        bytes memory value = delegateGetBytes(_testTarget, "dynamicallySizedValue()");
        require(value.length == bytes(dynamicallySizedValue).length &&
            keccak256(value) == keccak256(bytes(dynamicallySizedValue)));

        require(delegateGet(_testTarget, "getArrayValueLength()") == arrayValues.length);
        for (uint256 i = 0; i < arrayValues.length; i++) {
            require(delegateGet(_testTarget, "getArrayValue(uint256)", bytes32(i)) == arrayValues[i]);
        }
        for (uint256 i = 0; i < mappingIndices.length; i++) {
            uint256 index = mappingIndices[i];
            require(delegateGet(_testTarget, "getMappingValue(uint256)", bytes32(index)) == mappingValues[index]);
        }

        require(delegateGet(_testTarget, "getStructureLength1()") == arrayStructures.length);
        for (uint256 i = 0; i < arrayStructures.length; i++) {
            Structure1 memory structure1 = delegateGetStructure1(_testTarget, "arrayStructures(uint256)", bytes32(i));
            require(structure1.value == arrayStructures[i].value);
            require(delegateGet(_testTarget, "getStructureArrayLength1(uint256)", bytes32(i)) ==
                arrayStructures[i].arrayValues.length);
            for (uint256 j = 0; j < arrayStructures[i].arrayValues.length; j++) {
                require(delegateGet(
                        _testTarget, "getStructureArrayValue1(uint256,uint256)", bytes32(i), bytes32(j)) ==
                    arrayStructures[i].arrayValues[j]);
            }
        }

        require(delegateGet(_testTarget, "getStructureLength2()") == mappingStructuresLength);
        for (uint256 i = 0; i < mappingStructuresLength; i++) {
            Structure2 memory structure2 = delegateGetStructure2(_testTarget, "mappingStructures(uint256)", bytes32(i));
            require(structure2.value == mappingStructures[i].value);
            require(delegateGet(_testTarget, "getStructureArrayLength2(uint256)", bytes32(i)) ==
                mappingStructures[i].arrayValues.length);
            for (uint256 j = 0; j < mappingStructures[i].arrayValues.length; j++) {
                require(delegateGet(
                        _testTarget, "getStructureArrayValue2(uint256,uint256)", bytes32(i), bytes32(j)) ==
                    mappingStructures[i].arrayValues[j]);
            }
        }
    }

    function delegateGetStructure1(address _target, string memory _signature, bytes32 _argument)
        internal returns (Structure1 memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _signature, 1, _argument, 0);
        assembly {
            result := memoryAddress
        }
    }

    function delegateGetStructure2(address _target, string memory _signature, bytes32 _argument)
        internal returns (Structure2 memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _signature, 1, _argument, 0);
        assembly {
            result := memoryAddress
        }
    }

    function delegateGetBytes(address _target, string memory _signature)
        internal returns (bytes memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _signature, 0, 0, 0);
        assembly {
            result := add(memoryAddress, mload(memoryAddress))
        }
    }

    function finishUpgrade(address _target) public {
        super.finishUpgrade(_target);
        storageValue = ContractV1(_target).storageValue();
    }

    function createEvent(uint256 _value) public {
        emit EventV1(_value);
    }
}
