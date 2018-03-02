pragma solidity ^0.4.18;

// Note we don't need to use this interface (although it is advised if it's unlikely it will change).
// We can cast the UpgradableContractProxy as the specific implementations eg ContractV1.sol or ContractV2.sol.
// As can be seen in the getUpdatedDynamicallySizedValue() test case.
/**
* @dev Based on https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/upgradableImplementations/ContractInterface.sol
**/
contract ContractInterface {

    function returnValue() public pure returns (uint);

    function setStorageValue(uint _value) public;
    function getStorageValue() public view returns (uint);

    function setDynamicallySizedValue(string _dynamicValue) public;
    function getDynamicallySizedValue() public view returns (string);

    function pushArrayValue(uint _value) public;
    function getArrayValue(uint _index) public view returns (uint);
    function getArrayValueLength() public view returns (uint);

    function setMappingValue(uint _index, uint _value) public;
    function getMappingValue(uint _index) public view returns (uint);

    function getStructureLength1() public view returns (uint);
    function pushStructureValue1(uint _value) public;
    function getStructureValue1(uint _index) public view returns (uint);
    function getStructureArrayLength1(uint _index) public view returns (uint);
    function pushStructureArrayValue1(uint _index, uint _value) public;
    function getStructureArrayValue1(uint _index, uint _arrayIndex) public view returns (uint);

    function getStructureLength2() public view returns (uint);
    function pushStructureValue2(uint _value) public;
    function getStructureValue2(uint _index) public view returns (uint);
    function getStructureArrayLength2(uint _index) public view returns (uint);
    function pushStructureArrayValue2(uint _index, uint _value) public;
    function getStructureArrayValue2(uint _index, uint _arrayIndex) public view returns (uint);
}
