// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


import "contracts/proxy/Upgradeable.sol";


/**
* @dev Same test contract with explicit storage slots:
* The contract uses assembler code to access some storage variables instead of relying on the compiler
* This demonstrates how to mitigate possible changes in the compiler while using the proxy pattern
* Many methods are not optimized on purpose to increase readability
* see https://solidity.readthedocs.io/en/latest/miscellaneous.html#layout-of-state-variables-in-storage
*/
contract ContractV4 is Upgradeable {

    // slot allocation costs nothing
    // uint256 public storageValue;
    uint256 reservedSlot4;
    // string public dynamicallySizedValue;
    uint256 reservedSlot5;
    // uint256[] public arrayValues;
    uint256 reservedSlot6;
    // mapping (uint256 => uint256) public mappingValues;
    uint256 reservedSlot7;
    // uint256[] public mappingIndices;
    uint256 reservedSlot8;

    struct Structure1 {
        uint256 value;
        uint256[] arrayValues;
    }
    // Structure1[] public arrayStructures;
    uint256 reservedSlot9;

    struct Structure2 {
        uint256 value;
        uint256[] arrayValues;
        uint256 valueToCheck;
    }
    // mapping (uint256 => Structure2) public mappingStructures;
    uint256 reservedSlot10;
    // uint256 public mappingStructuresLength;
    uint256 reservedSlot11;

    // uint256 public storageValueToCheck;
    uint256 reservedSlot12;
    uint256 public anotherStorageValue;

    constructor(uint256 _storageValueToCheck) {
        setStorageValueToCheck(_storageValueToCheck);
    }

    function returnValue() public pure returns (uint256) {
        return 30;
    }


    /// @dev Get data from the specified slot
    function getValue(uint256 _slotNumber) public view returns (uint256 value) {
        assembly {
            value := sload(_slotNumber)
        }
    }

    /// @dev Array data is in the slot keccak256(_slotNumber)+_index
    function getArraySlot(uint256 _slotNumber, uint256 _index) private pure returns (uint256 slot) {
        assembly {
            // put data for hash into a free memory
            let memoryAddress := mload(0x40)
            mstore(memoryAddress, _slotNumber)
            let baseSlot := keccak256(memoryAddress, 32)
            slot := add(baseSlot, _index)
        }
    }
    function getArrayValue(uint256 _slotNumber, uint256 _index) private view returns (uint256 value) {
        return getValue(getArraySlot(_slotNumber, _index));
    }

    /// @dev Mapping data is in the slot keccak256(concat(_index, _slotNumber))
    function getMappingSlot(uint256 _slotNumber, uint256 _index) private pure returns (uint256 slot) {
        assembly {
            let memoryAddress := mload(0x40)
            mstore(memoryAddress, _index)
            mstore(add(memoryAddress, 32), _slotNumber)
            slot := keccak256(memoryAddress, 64)
        }
    }
    function getMappingValue(uint256 _slotNumber, uint256 _index) private view returns (uint256 value) {
        return getValue(getMappingSlot(_slotNumber, _index));
    }


    function storageValue() public view returns (uint256 value) {
        // storageValue in the slot number 4
        return getValue(4);
    }

    function dynamicallySizedValue() public view returns (string memory value) {
        uint256 slotValue = getValue(5);
        // https://solidity.readthedocs.io/en/latest/miscellaneous.html#bytes-and-string
        uint8 lowestBit = uint8(slotValue & 1);
        if (lowestBit == 0) {
            uint8 length = uint8(bytes32(slotValue)[31]) / 2;
            value = new string(length);
            assembly {
                mstore(add(value, 32), slotValue)
                mstore8(add(value, 63), 0)
            }
        } else {
            uint256 length = (slotValue - 1) / 2;
            value = new string(length);
            uint256 wordsCount = (length - 1) / 32 + 1;
            for (uint256 i = 0; i < wordsCount; i++) {
                uint256 word = getArrayValue(4, i);
                uint256 offset = 32 * (i + 1);
                assembly {
                    mstore(add(value, offset), word)
                }
            }
        }
    }

    function getArrayValueLength() public view returns (uint256) {
        // length of the array in the slot number 6
        return getValue(6);
    }
    function arrayValues(uint256 _index) public view returns (uint256) {
        require(_index < getArrayValueLength());
        // base slot for this array is 6
        return getArrayValue(6, _index);
    }


    function mappingValues(uint256 _index) public view returns (uint256) {
        // base slot for this mapping is 7
        return getMappingValue(7, _index);
    }
    function getMappingIndicesLength() public view returns (uint256) {
        // length of the array in the slot number
        return getValue(8);
    }
    function mappingIndices(uint256 _index) public view returns (uint256) {
        require(_index < getMappingIndicesLength());
        return getArrayValue(8, _index);
    }


    function getStructureLength1() public view returns (uint256) {
        // length of the array in the slot number 9
        return getValue(9);
    }
    function arrayStructures(uint256 _index) public view returns (uint256) {
        require(_index < getStructureLength1());
        // base slot for this array is 9
        // one value in this array is `value` and the length of the inner `arrayValues`
        // so each index represents 2 slots
        return getArrayValue(9, 2 * _index);
    }
    function getStructureArrayLength1(uint256 _index) public view returns (uint256) {
        require(_index < getStructureLength1());
        // same as above except accessing second part of the value
        return getArrayValue(9, 2 * _index + 1);
    }
    /// @dev Array data is in the slot keccak256(keccak256(9) + 2 * _index + 1) + _arrayIndex
    function getStructureArrayValue1(uint256 _index, uint256 _arrayIndex) public view returns (uint256) {
        require(_arrayIndex < getStructureArrayLength1(_index));
        uint256 baseSlot = getArraySlot(9, 2 * _index + 1);
        return getArrayValue(baseSlot, _arrayIndex);
    }
    function getStructure1ArrayValues(uint256 _index) public view returns (uint256[] memory result) {
        result = new uint256[](getStructureArrayLength1(_index));
        uint256 baseSlot = getArraySlot(9, 2 * _index + 1);
        for (uint256 i = 0; i < result.length; i++) {
            result[i] = getArrayValue(baseSlot, i);
        }
    }

    function getStructureLength2() public view returns (uint256) {
        return getValue(11);
    }
    function mappingStructures(uint256 _index) public view returns (uint256 value, uint256 valueToCheck) {
        uint256 baseMappingSlot = getMappingSlot(10, _index);
        // one mapping value is `value`,  the length of the inner `arrayValues` and `valueToCheck`
        value = getValue(baseMappingSlot);
        valueToCheck = getValue(baseMappingSlot + 2);
    }
    function getStructureArrayLength2(uint256 _index) public view returns (uint256) {
        return getValue(getMappingSlot(10, _index) + 1);
    }
    /// @dev Array data is in the slot keccak256(keccak256(concat(_index, 11)) + 1) + _arrayIndex
    function getStructureArrayValue2(uint256 _index, uint256 _arrayIndex) public view returns (uint256) {
        require(_arrayIndex < getStructureArrayLength2(_index));
        uint256 baseArraySlot = getMappingSlot(10, _index) + 1;
        return getArrayValue(baseArraySlot, _arrayIndex);
    }
    function getStructure2ArrayValues(uint256 _index) public view returns (uint256[] memory result) {
        result = new uint256[](getStructureArrayLength2(_index));
        uint256 baseArraySlot = getMappingSlot(10, _index) + 1;
        for (uint256 i = 0; i < result.length; i++) {
            result[i] = getArrayValue(baseArraySlot, i);
        }
    }

    function storageValueToCheck() public view returns (uint256) {
        return getValue(12);
    }
    function setStorageValueToCheck(uint256 _value) public {
        assembly {
            sstore(12, _value)
        }
    }

    function verifyState(address _testTarget) public override {
        super.verifyState(_testTarget);
        require(delegateGet(_testTarget, this.storageValue.selector) == storageValue());
        bytes memory value = delegateGetBytes(_testTarget, this.dynamicallySizedValue.selector);
        bytes memory originalValue = bytes(dynamicallySizedValue());
        require(value.length == originalValue.length &&
            keccak256(value) == keccak256(originalValue));

        uint256 length = getArrayValueLength();
        require(delegateGet(_testTarget, this.getArrayValueLength.selector) == length);
        for (uint256 i = 0; i < length; i++) {
            require(delegateGet(_testTarget, this.arrayValues.selector, bytes32(i)) == arrayValues(i));
        }
        length = getMappingIndicesLength();
        for (uint256 i = 0; i < length; i++) {
            uint256 index = mappingIndices(i);
            require(delegateGet(_testTarget, this.mappingValues.selector, bytes32(index)) == mappingValues(index));
        }

        length = getStructureLength1();
        require(delegateGet(_testTarget, this.getStructureLength1.selector) == length);
        for (uint256 i = 0; i < length; i++) {
            require(delegateGet(_testTarget, this.arrayStructures.selector, bytes32(i)) == arrayStructures(i));

            uint256 structuresLength = getStructureArrayLength1(i);
            require(delegateGet(_testTarget, this.getStructureArrayLength1.selector, bytes32(i)) == structuresLength);
            for (uint256 j = 0; j < structuresLength; j++) {
                require(delegateGet(
                        _testTarget, this.getStructureArrayValue1.selector, bytes32(i), bytes32(j)) ==
                    getStructureArrayValue1(i, j));
            }
        }

        length = getStructureLength2();
        require(delegateGet(_testTarget, this.getStructureLength2.selector) == length);
        for (uint256 i = 0; i < length; i++) {
            Structure2 memory structure2 = delegateGetStructure2(_testTarget, this.mappingStructures.selector, bytes32(i));
            (uint256 structureValue, uint256 structureValueToCheck) = mappingStructures(i);
            require(structureValue == structure2.value && structureValueToCheck == structure2.valueToCheck);

            uint256 structuresLength = getStructureArrayLength2(i);
            require(delegateGet(_testTarget, this.getStructureArrayLength2.selector, bytes32(i)) == structuresLength);
            for (uint256 j = 0; j < structuresLength; j++) {
                require(delegateGet(
                        _testTarget, this.getStructureArrayValue2.selector, bytes32(i), bytes32(j)) ==
                    getStructureArrayValue2(i, j));
            }
        }

        require(delegateGet(_testTarget, this.storageValueToCheck.selector) == storageValueToCheck());
        require(delegateGet(_testTarget, this.anotherStorageValue.selector) == anotherStorageValue);
    }

    function delegateGetStructure2(address _target, bytes4 _selector, bytes32 _argument)
        internal returns (Structure2 memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _selector, 1, _argument, 0);
        assembly {
            mstore(result, mload(memoryAddress))
            mstore(add(result, 64), mload(add(memoryAddress, 32)))
        }
    }

    function delegateGetBytes(address _target, bytes4 _selector)
        internal returns (bytes memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _selector, 0, 0, 0);
        assembly {
            // weird problems with copying the memory pointer:
            // result := add(memoryAddress, mload(memoryAddress))

            // and with quick fix for tests - copy the beginning of the array
            // let start := add(memoryAddress, mload(memoryAddress))
            // mstore(result, mload(start))
            // mstore(add(result, 32), mload(add(start, 32)))

            result := memoryAddress
        }
    }

    function finishUpgrade(address _target) public override {
        super.finishUpgrade(_target);
        setStorageValueToCheck(ContractV4(_target).storageValueToCheck());
    }

}
