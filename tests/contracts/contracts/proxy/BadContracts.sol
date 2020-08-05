// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


import "./ContractV1.sol";
import "contracts/proxy/Upgradeable.sol";


/**
* @dev This contract can't be target for dispatcher because missed `previousTarget`
*/
contract BadDispatcherStorage {

    address public owner;
    address public target;
//    address public previousTarget;
    uint8 public isUpgrade;

    function verifyState(address _testTarget) public {}
    function finishUpgrade(address _target) public {}

}


/**
* @dev Upgrade to this contract will fail because added `fakeValue`
*/
contract ContractV2BadStorage is Upgradeable {

    // TODO can't catch such a violation
//    uint128 public storageValue;
    uint256 public storageValue;
    uint128 public fakeValue;
    string public dynamicallySizedValue;
    uint256[] arrayValues;
    mapping (uint256 => uint256) mappingValues;
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

    function verifyState(address) public override {}
    function finishUpgrade(address) public override {}

}


/**
* @dev Upgrade to this contract will fail because `verifyState` is broken
*/
contract ContractV2BadVerifyState is ContractV1(1) {

    function verifyState(address) public pure override {
        revert();
    }

}
