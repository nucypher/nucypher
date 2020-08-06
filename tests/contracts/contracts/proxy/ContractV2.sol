// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


import "contracts/proxy/Upgradeable.sol";


/**
* @dev Extension of the contract using valid storage variables
*/
contract ContractV2 is Upgradeable {

    event EventV2(uint8 value);

    uint256 public storageValue;
    string public dynamicallySizedValue;
    uint256[] public arrayValues;
    mapping (uint256 => uint256) public mappingValues;
    uint256[] public mappingIndices;

    struct Structure1 {
        uint256 value;
        uint256[] arrayValues;
    }
    Structure1[] public arrayStructures;

    struct Structure2 {
        uint256 value;
        uint256[] arrayValues;
        uint256 valueToCheck;
    }
    mapping (uint256 => Structure2) public mappingStructures;
    uint256 public mappingStructuresLength;

    uint256 public storageValueToCheck;

    constructor(uint256 _storageValueToCheck) {
        storageValueToCheck = _storageValueToCheck;
    }

    function returnValue() public pure returns (uint256) {
        return 20;
    }

    function setStorageValue(uint256 _value) public {
        storageValue = _value * 2;
    }

    function setDynamicallySizedValue(string memory _dynamicValue) public {
        dynamicallySizedValue = _dynamicValue;
    }

    function pushArrayValue(uint256 _value) public {
        arrayValues.push(2 * _value);
    }
    function getArrayValueLength() public view returns (uint256) {
        return arrayValues.length;
    }

    function setMappingValue(uint256 _index, uint256 _value) public {
        mappingIndices.push(_index);
        mappingValues[_index] = _value;
    }

    function getStructureLength1() public view returns (uint256) {
        return arrayStructures.length;
    }
    function pushStructureValue1(uint256 _value) public {
        Structure1 memory structure;
        arrayStructures.push(structure);
        arrayStructures[arrayStructures.length - 1].value = _value;
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
    function getStructureArrayLength2(uint256 _index) public view returns (uint256) {
        return mappingStructures[_index].arrayValues.length;
    }
    function pushStructureArrayValue2(uint256 _index, uint256 _value) public {
        mappingStructures[_index].arrayValues.push(_value);
    }
    function getStructureArrayValue2(uint256 _index, uint256 _arrayIndex) public view returns (uint256) {
        return mappingStructures[_index].arrayValues[_arrayIndex];
    }

    function setStructureValueToCheck2(uint256 _index, uint256 _value) public {
        mappingStructures[_index].valueToCheck = _value;
    }

    function getStructure1ArrayValues(uint256 _index) public view returns (uint256[] memory) {
        return arrayStructures[_index].arrayValues;
    }

    function getStructure2ArrayValues(uint256 _index) public view returns (uint256[] memory) {
        return mappingStructures[_index].arrayValues;
    }

    function verifyState(address _testTarget) public override virtual {
        super.verifyState(_testTarget);
        require(delegateGet(_testTarget, this.storageValue.selector) == storageValue);
        bytes memory value = delegateGetBytes(_testTarget, this.dynamicallySizedValue.selector);
        require(value.length == bytes(dynamicallySizedValue).length &&
            keccak256(value) == keccak256(bytes(dynamicallySizedValue)));

        require(delegateGet(_testTarget, this.getArrayValueLength.selector) == arrayValues.length);
        for (uint256 i = 0; i < arrayValues.length; i++) {
            require(delegateGet(_testTarget, this.arrayValues.selector, bytes32(i)) == arrayValues[i]);
        }
        for (uint256 i = 0; i < mappingIndices.length; i++) {
            uint256 index = mappingIndices[i];
            require(delegateGet(_testTarget, this.mappingValues.selector, bytes32(index)) ==
                mappingValues[index]);
        }

        require(delegateGet(_testTarget, this.getStructureLength1.selector) == arrayStructures.length);
        for (uint256 i = 0; i < arrayStructures.length; i++) {
            require(delegateGet(_testTarget, this.arrayStructures.selector, bytes32(i)) == arrayStructures[i].value);

            uint256[] memory values = delegateGetArray(_testTarget, this.getStructure1ArrayValues.selector, bytes32(i));
            require(values.length == arrayStructures[i].arrayValues.length);
            for (uint256 j = 0; j < arrayStructures[i].arrayValues.length; j++) {
                require(values[j] == arrayStructures[i].arrayValues[j]);
            }
        }

        require(delegateGet(_testTarget, this.getStructureLength2.selector) == mappingStructuresLength);
        for (uint256 i = 0; i < mappingStructuresLength; i++) {
            Structure2 memory structure2 = delegateGetStructure2(_testTarget, this.mappingStructures.selector, bytes32(i));
            require(structure2.value == mappingStructures[i].value);
            require(structure2.valueToCheck == mappingStructures[i].valueToCheck);

            uint256[] memory values = delegateGetArray(_testTarget, this.getStructure2ArrayValues.selector, bytes32(i));
            require(values.length == mappingStructures[i].arrayValues.length);
            for (uint256 j = 0; j < mappingStructures[i].arrayValues.length; j++) {
                require(values[j] == mappingStructures[i].arrayValues[j]);
            }
        }

        require(delegateGet(_testTarget, this.storageValueToCheck.selector) == storageValueToCheck);
    }

    function delegateGetStructure2(address _target, bytes4 _selector, bytes32 _argument)
        internal returns (Structure2 memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _selector, 1, _argument, 0);
        assembly {
            result := memoryAddress
            // copy data to the right position because of it is the array pointer place (arrayValues)
            mstore(add(memoryAddress, 0x40), mload(add(memoryAddress, 0x20)))
        }
    }

    function delegateGetBytes(address _target, bytes4 _selector)
        internal returns (bytes memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _selector, 0, 0, 0);
        assembly {
            result := add(memoryAddress, mload(memoryAddress))
        }
    }

    /**
    * @dev Get array by one parameter.
    */
    function delegateGetArray(
        address _target,
        bytes4 _selector,
        bytes32 _argument
    )
        public returns (uint256[] memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _selector, 1, _argument, 0);
        assembly {
            result := add(memoryAddress, mload(memoryAddress))
        }
    }

    function finishUpgrade(address _target) public override {
        super.finishUpgrade(_target);
        storageValueToCheck = ContractV2(_target).storageValueToCheck();
    }

    function createEvent(uint8 _value) public {
        emit EventV2(_value);
    }
}
