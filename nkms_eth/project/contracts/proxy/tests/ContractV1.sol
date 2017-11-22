pragma solidity ^0.4.18;


import "./ContractInterface.sol";
import "../../zeppelin/ownership/Ownable.sol";


/**
* @dev Copied from https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/upgradableImplementations/ContractV1.sol
**/
contract ContractV1 is ContractInterface, Ownable {

    // Stored data actually lives in the UpgradableContractProxy. However the storage layout is specified here in the implementing contracts.
    // The first and only variable in the UpgradableContractProxy is a reference to the address of this contract.
    // Therefore the first reference in each contract using the UpgradableContractProxy must be set aside for this address.
    address private target;

    // The storage layout must remain the same in all the upgraded contracts, although it can be added to.
    // Note that besides the potential mess of unnecessary variables this could create over time, there isn't currently
    // any increase in cost because of this.
    uint public storageValue;
    string public dynamicallySizedValue;

    function returnValue() public constant returns (uint) {
        return 10;
    }

    function setStorageValue(uint value) public {
        storageValue = value;
    }

    // We can't use the automatically created getter methods for public vars if
    // we want them to be updatable because we can't specify them in an interface.
    function getStorageValue() public constant returns (uint) {
        return storageValue;
    }

    function setDynamicallySizedValue(string dynamicValue) public {
        dynamicallySizedValue = dynamicValue;
    }

    function getDynamicallySizedValue() public constant returns (string) {
        return dynamicallySizedValue;
    }

}
