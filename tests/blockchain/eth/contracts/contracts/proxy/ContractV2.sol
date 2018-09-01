pragma solidity ^0.4.24;


import "./ContractInterface.sol";
import "contracts/proxy/Upgradeable.sol";


/**
* @dev Based on https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/upgradableImplementations/ContractV2.sol
**/
contract ContractV2 is ContractInterface, Upgradeable {

    event EventV2(uint8 value);

    uint public storageValue;
    string public dynamicallySizedValue;
    uint[] public arrayValues;
    mapping (uint => uint) mappingValues;
    uint[] public mappingIndices;

    struct Structure1 {
        uint value;
        uint[] arrayValues;
//        uint valueToCheck; // rollback does not work
    }
    Structure1[] public arrayStructures;

    struct Structure2 {
        uint value;
        uint[] arrayValues;
        uint valueToCheck;
    }
    mapping (uint => Structure2) public mappingStructures;
    uint public mappingStructuresLength;

    uint public storageValueToCheck;

    constructor(uint _storageValueToCheck) public {
        storageValueToCheck = _storageValueToCheck;
    }

    function returnValue() public pure returns (uint) {
        return 20;
    }

    function setStorageValue(uint _value) public {
        storageValue = _value * 2;
    }
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
        arrayValues.push(2 * _value);
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

    function setStructureValueToCheck2(uint _index, uint _value) public {
        mappingStructures[_index].valueToCheck = _value;
    }
    function getStructureValueToCheck2(uint _index) public view returns (uint) {
        return mappingStructures[_index].valueToCheck;
    }

    function getStructure1ArrayValues(uint _index) public view returns (uint[]) {
        return arrayStructures[_index].arrayValues;
    }

    function getStructure2ArrayValues(uint _index) public view returns (uint[]) {
        return mappingStructures[_index].arrayValues;
    }

    function verifyState(address _testTarget) public onlyOwner {
        require(uint(delegateGet(_testTarget, "storageValue()")) == storageValue);
        bytes memory value = delegateGetBytes(_testTarget, "dynamicallySizedValue()");
        require(value.length == bytes(dynamicallySizedValue).length &&
            keccak256(value) == keccak256(bytes(dynamicallySizedValue)));

        require(uint(delegateGet(_testTarget, "getArrayValueLength()")) == arrayValues.length);
        for (uint i = 0; i < arrayValues.length; i++) {
            require(
                uint(delegateGet(_testTarget, "getArrayValue(uint256)", bytes32(i))) == arrayValues[i]);
        }
        for (i = 0; i < mappingIndices.length; i++) {
            uint index = mappingIndices[i];
            require(uint(delegateGet(_testTarget, "getMappingValue(uint256)", bytes32(index))) ==
                mappingValues[index]);
        }

        require(uint(delegateGet(_testTarget, "getStructureLength1()")) == arrayStructures.length);
        for (i = 0; i < arrayStructures.length; i++) {
            Structure1 memory structure1 = delegateGetStructure1(_testTarget, "arrayStructures(uint256)", bytes32(i));
            require(structure1.value == arrayStructures[i].value);

            bytes32[] memory values = delegateGetArray(_testTarget, "getStructure1ArrayValues(uint256)", bytes32(i));
            require(values.length == arrayStructures[i].arrayValues.length);
            for (uint j = 0; j < arrayStructures[i].arrayValues.length; j++) {
                require(uint(values[j]) == arrayStructures[i].arrayValues[j]);
            }
        }

        require(uint(delegateGet(_testTarget, "getStructureLength2()")) == mappingStructuresLength);
        for (i = 0; i < mappingStructuresLength; i++) {
            Structure2 memory structure2 = delegateGetStructure2(_testTarget, "mappingStructures(uint256)", bytes32(i));
            require(structure2.value == mappingStructures[i].value);
            require(structure2.valueToCheck == mappingStructures[i].valueToCheck);

            values = delegateGetArray(_testTarget, "getStructure2ArrayValues(uint256)", bytes32(i));
            require(values.length == mappingStructures[i].arrayValues.length);
            for (j = 0; j < mappingStructures[i].arrayValues.length; j++) {
                require(uint(values[j]) == mappingStructures[i].arrayValues[j]);
            }
        }

        require(uint(delegateGet(_testTarget, "storageValueToCheck()")) == storageValueToCheck);
    }

    function delegateGetStructure1(address _target, string _signature, bytes32 _argument)
        internal returns (Structure1 memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _signature, 1, _argument, 0);
        assembly {
            result := memoryAddress
        }
    }

    function delegateGetStructure2(address _target, string _signature, bytes32 _argument)
        internal returns (Structure2 memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _signature, 1, _argument, 0);
        assembly {
            result := memoryAddress
            // copy data to the right position because of it is the array pointer place (arrayValues)
            mstore(add(memoryAddress, 0x40), mload(add(memoryAddress, 0x20)))
        }
    }

    function delegateGetBytes(address _target, string _signature)
        internal returns (bytes memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _signature, 0, 0, 0);
        assembly {
            result := add(memoryAddress, mload(memoryAddress))
        }
    }

    /**
    * @dev Get array by one parameter.
    **/
    function delegateGetArray(
        address _target,
        string _signature,
        bytes32 _argument
    )
        public returns (bytes32[] memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _signature, 1, _argument, 0);
        assembly {
            result := add(memoryAddress, mload(memoryAddress))
        }
    }

    function finishUpgrade(address _target) public onlyOwner {
        storageValueToCheck = ContractV2(_target).storageValueToCheck();
    }

    function createEvent(uint8 _value) public {
        emit EventV2(_value);
    }
}
