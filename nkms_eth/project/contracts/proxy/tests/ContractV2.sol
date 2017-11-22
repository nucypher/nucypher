pragma solidity ^0.4.18;


import "./ContractInterface.sol";
import "../../zeppelin/ownership/Ownable.sol";


/**
* @dev Copied from https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/upgradableImplementations/ContractV2.sol
**/
contract ContractV2 is ContractInterface, Ownable {

    address private target;

    uint public storageValue;
    string public dynamicallySizedValue;
    uint[] public updatedDynamicallySizedValue;

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
}
