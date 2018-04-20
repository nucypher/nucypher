pragma solidity ^0.4.18;


import "./ContractInterface.sol";
import "proxy/Upgradeable.sol";


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

    uint[] public updatedDynamicallySizedValue;
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

    function setDynamicallySizedValue(string) public {}
    function getDynamicallySizedValue() public view returns (string) {}

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

    /**
     * @notice The 2 functions below represent newly updated functions returning a different dynamically sized value.
     *         Ideally we would do our best to avoid changing the signature of updated functions.
     *         If adhering to an interface we have to update it and everywhere the interface is used.
     */
    function setDynamicallySizedValue(uint[] _updatedDynamicallySizedValue) public {
        updatedDynamicallySizedValue = _updatedDynamicallySizedValue;
    }
    /**
     * @notice This new function signature must be different than the one in the interface.
     *         Note the return value does not contribute to the signature.
     */
    function getUpdatedDynamicallySizedValue() public view returns (uint[]) {
        return updatedDynamicallySizedValue;
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

    function verifyState(address _testTarget) public onlyOwner {
        require(uint(delegateGet(_testTarget, "storageValue()")) == storageValue);
        //TODO uncomment after fixing return size
//        require(address(delegateGet(_testTarget, "dynamicallySizedValue()")) == owner);
//        require(address(delegateGet(_testTarget, "updatedDynamicallySizedValue()")) == owner);
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
            require(uint(delegateGet(_testTarget, "getStructureValueToCheck2(uint256)", bytes32(i))) ==
                mappingStructures[i].valueToCheck);
        }

        require(uint(delegateGet(_testTarget, "storageValueToCheck()")) == storageValueToCheck);
    }

    function finishUpgrade(address _target) public onlyOwner {
        storageValueToCheck = ContractV2(_target).storageValueToCheck();
    }

    function createEvent(uint8 _value) public {
        emit EventV2(_value);
    }
}
