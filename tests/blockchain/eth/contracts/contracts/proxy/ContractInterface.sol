pragma solidity ^0.5.3;

// Note we don't need to use this interface (although it is advised if it's unlikely it will change).
// We can cast the UpgradableContractProxy as the specific implementations eg ContractV1.sol or ContractV2.sol.
// As can be seen in the getUpdatedDynamicallySizedValue() test case.
/**
* @dev Based on https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/upgradableImplementations/ContractInterface.sol
**/
contract ContractInterface {

    function returnValue() public pure returns (uint256);

    function setStorageValue(uint256 _value) public;
    function getStorageValue() public view returns (uint256);

    function setDynamicallySizedValue(string memory _dynamicValue) public;
    function getDynamicallySizedValue() public view returns (string memory);

    function pushArrayValue(uint256 _value) public;
    function getArrayValue(uint256 _index) public view returns (uint256);
    function getArrayValueLength() public view returns (uint256);

    function setMappingValue(uint256 _index, uint256 _value) public;
    function getMappingValue(uint256 _index) public view returns (uint256);

    function getStructureLength1() public view returns (uint256);
    function pushStructureValue1(uint256 _value) public;
    function getStructureValue1(uint256 _index) public view returns (uint256);
    function getStructureArrayLength1(uint256 _index) public view returns (uint256);
    function pushStructureArrayValue1(uint256 _index, uint256 _value) public;
    function getStructureArrayValue1(uint256 _index, uint256 _arrayIndex) public view returns (uint256);

    function getStructureLength2() public view returns (uint256);
    function pushStructureValue2(uint256 _value) public;
    function getStructureValue2(uint256 _index) public view returns (uint256);
    function getStructureArrayLength2(uint256 _index) public view returns (uint256);
    function pushStructureArrayValue2(uint256 _index, uint256 _value) public;
    function getStructureArrayValue2(uint256 _index, uint256 _arrayIndex) public view returns (uint256);
}
