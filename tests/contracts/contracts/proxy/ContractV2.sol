pragma solidity ^0.4.18;


import "./ContractInterface.sol";
import "contracts/proxy/Upgradeable.sol";


/**
* @dev Based on https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/upgradableImplementations/ContractV2.sol
**/
contract ContractV2 is ContractInterface, Upgradeable {

    uint public storageValue;
    string public dynamicallySizedValue;
    uint[] public arrayValues;
    mapping (uint => uint) mappingValues;
    uint[] public mappingIndices;

    struct Structure {
        uint value;
        uint[] arrayValues;
//        uint valueToCheck; // rollback does not work
    }
    Structure[] public structures;

    uint[] public updatedDynamicallySizedValue;
    uint public storageValueToCheck;

    function returnValue() public constant returns (uint) {
        return 20;
    }

    function setStorageValue(uint value) public {
        storageValue = value * 2;
    }

    function getStorageValue() public constant returns (uint) {
        return storageValue;
    }

    function setDynamicallySizedValue(string dynamicValue) public {}

    function getDynamicallySizedValue() public constant returns (string) {}

    function pushArrayValue(uint value) public {
        arrayValues.push(2 * value);
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
    function getUpdatedDynamicallySizedValue() public constant returns (uint[]) {
        return updatedDynamicallySizedValue;
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
//        require(address(delegateGet(testTarget, "updatedDynamicallySizedValue()")) == owner);
        require(uint(delegateGet(testTarget, "getArrayValueLength()")) == arrayValues.length);
        for (uint i = 0; i < arrayValues.length; i++) {
            require(
                uint(delegateGet(testTarget, "getArrayValue(uint256)", bytes32(i))) == arrayValues[i]);
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

        require(uint(delegateGet(testTarget, "storageValueToCheck()")) == storageValueToCheck);
    }
}
