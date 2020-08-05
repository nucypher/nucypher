// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


import "contracts/proxy/Upgradeable.sol";


/**
* @dev Base contract for testing upgrading using dispatcher
*/
contract ContractV1 is Upgradeable {

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

    constructor(uint256 _storageValue) {
        storageValue = _storageValue;
    }

    function returnValue() public pure returns (uint256) {
        return 10;
    }

    function setStorageValue(uint256 _value) public {
        storageValue = _value;
    }

    function setDynamicallySizedValue(string memory _dynamicValue) public {
        dynamicallySizedValue = _dynamicValue;
    }

    function pushArrayValue(uint256 _value) public {
        arrayValues.push(_value);
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

    function verifyState(address _testTarget) public override virtual {
        super.verifyState(_testTarget);
        require(delegateGet(_testTarget, this.storageValue.selector) == storageValue);
        bytes memory value = delegateGetBytes(_testTarget, this.dynamicallySizedValue.selector);
        // WARNING: sometimes execution of keccak256(string storage) on a long string (more than 31 bytes)
        // leads to out of gas or exception
        require(value.length == bytes(dynamicallySizedValue).length &&
            keccak256(value) == keccak256(bytes(dynamicallySizedValue)));

        require(delegateGet(_testTarget, this.getArrayValueLength.selector) == arrayValues.length);
        for (uint256 i = 0; i < arrayValues.length; i++) {
            require(delegateGet(_testTarget, this.arrayValues.selector, bytes32(i)) == arrayValues[i]);
        }
        for (uint256 i = 0; i < mappingIndices.length; i++) {
            uint256 index = mappingIndices[i];
            require(delegateGet(_testTarget, this.mappingValues.selector, bytes32(index)) == mappingValues[index]);
        }

        require(delegateGet(_testTarget, this.getStructureLength1.selector) == arrayStructures.length);
        for (uint256 i = 0; i < arrayStructures.length; i++) {
            require(delegateGet(_testTarget, this.arrayStructures.selector, bytes32(i)) == arrayStructures[i].value);

            require(delegateGet(_testTarget, this.getStructureArrayLength1.selector, bytes32(i)) ==
                arrayStructures[i].arrayValues.length);
            for (uint256 j = 0; j < arrayStructures[i].arrayValues.length; j++) {
                require(delegateGet(
                        _testTarget, this.getStructureArrayValue1.selector, bytes32(i), bytes32(j)) ==
                    arrayStructures[i].arrayValues[j]);
            }
        }

        require(delegateGet(_testTarget, this.getStructureLength2.selector) == mappingStructuresLength);
        for (uint256 i = 0; i < mappingStructuresLength; i++) {
            require(delegateGet(_testTarget, this.mappingStructures.selector, bytes32(i)) == mappingStructures[i].value);

            require(delegateGet(_testTarget, this.getStructureArrayLength2.selector, bytes32(i)) ==
                mappingStructures[i].arrayValues.length);
            for (uint256 j = 0; j < mappingStructures[i].arrayValues.length; j++) {
                require(delegateGet(
                        _testTarget, this.getStructureArrayValue2.selector, bytes32(i), bytes32(j)) ==
                    mappingStructures[i].arrayValues[j]);
            }
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

    function finishUpgrade(address _target) public override {
        super.finishUpgrade(_target);
        storageValue = ContractV1(_target).storageValue();
    }

    function createEvent(uint256 _value) public {
        emit EventV1(_value);
    }
}
