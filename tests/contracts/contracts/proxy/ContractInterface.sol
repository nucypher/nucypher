pragma solidity ^0.4.18;

// Note we don't need to use this interface (although it is advised if it's unlikely it will change).
// We can cast the UpgradableContractProxy as the specific implementations eg ContractV1.sol or ContractV2.sol.
// As can be seen in the getUpdatedDynamicallySizedValue() test case.
/**
* @dev Based on https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/upgradableImplementations/ContractInterface.sol
**/
contract ContractInterface {

    function returnValue() public constant returns (uint);

    function setStorageValue(uint value) public;
    function getStorageValue() public constant returns (uint);

    function setDynamicallySizedValue(string dynamicValue) public;
    function getDynamicallySizedValue() public constant returns (string);

    function pushArrayValue(uint value) public;
    function getArrayValue(uint index) public constant returns (uint);
    function getArrayValueLength() public constant returns (uint);

    function setMappingValue(uint index, uint value) public;
    function getMappingValue(uint index) public constant returns (uint);

    function getStructureLength1() public constant returns (uint);
    function pushStructureValue1(uint value) public;
    function getStructureValue1(uint index) public constant returns (uint);
    function getStructureArrayLength1(uint index) public constant returns (uint);
    function pushStructureArrayValue1(uint index, uint value) public;
    function getStructureArrayValue1(uint index, uint arrayIndex) public constant returns (uint);

    function getStructureLength2() public constant returns (uint);
    function pushStructureValue2(uint value) public;
    function getStructureValue2(uint index) public constant returns (uint);
    function getStructureArrayLength2(uint index) public constant returns (uint);
    function pushStructureArrayValue2(uint index, uint value) public;
    function getStructureArrayValue2(uint index, uint arrayIndex) public constant returns (uint);
}
