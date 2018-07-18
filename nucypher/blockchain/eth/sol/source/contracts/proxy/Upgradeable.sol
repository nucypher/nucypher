pragma solidity ^0.4.23;


import "zeppelin/ownership/Ownable.sol";


/**
* @notice Base contract for upgradeable contract
* @dev Inherited contract should implement verifyState(address) method by checking storage variables
* (see verifyState(address) in Dispatcher). Also contract  should implement finishUpgrade(address)
* if it is using constructor parameters by coping this parameters to the dispatcher storage
**/
contract Upgradeable is Ownable {

    /**
    * @dev Contracts at the target must reserve the first location in storage for this address as
    * they will be called through this contract.
    * Stored data actually lives in the Dispatcher.
    * However the storage layout is specified here in the implementing contracts.
    **/
    address public target;

    /**
    * @dev Previous contract address (if available). Used for rollback
    **/
    address public previousTarget;

    /**
    * @dev Secret hash to proof that user owns previous version of a contract
    **/
    bytes32 public secretHash;

    /**
    * @dev Method for verifying storage state.
    * Should check that new target contract returns right storage value
    **/
    function verifyState(address _testTarget) public /*onlyOwner*/;

    /**
    * @dev Copy values from the new target to the current storage
    * @param _target New target contract address
    **/
    function finishUpgrade(address _target) public /*onlyOwner*/;

    /**
    * @dev Base method to get data
    * @param _target Target to call
    * @param _signature Method signature
    * @param _numberOfArguments Number of used arguments
    * @param _argument1 First method argument
    * @param _argument2 Second method argument
    * @return Address in memory where the data is located
    **/
    function delegateGetData(
        address _target,
        string _signature,
        uint8 _numberOfArguments,
        bytes32 _argument1,
        bytes32 _argument2
    )
        internal returns (bytes32 memoryAddress)
    {
        bytes4 targetCall = bytes4(keccak256(abi.encodePacked(_signature)));
        assembly {
            let freeMemAddress := mload(0x40)
            mstore(freeMemAddress, targetCall)
            if gt(_numberOfArguments, 0) {
                mstore(add(freeMemAddress, 0x04), _argument1)
            }
            if gt(_numberOfArguments, 1) {
                mstore(add(freeMemAddress, 0x24), _argument2)
            }
            switch delegatecall(gas, _target, freeMemAddress, add(0x04, mul(0x20, _numberOfArguments)), 0, 0)
                case 0 {
                    revert(freeMemAddress, 0)
                }
                default {
                    returndatacopy(freeMemAddress, 0x0, returndatasize)
                    memoryAddress := freeMemAddress
                }
        }
    }

    /**
    * @dev Call "getter" without parameters.
    * Result should not exceed 32 bytes
    **/
    function delegateGet(address _target, string _signature)
        internal returns (bytes32 result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _signature, 0, 0, 0);
        assembly {
            result := mload(memoryAddress)
        }
    }

    /**
    * @dev Call "getter" with one parameter.
    * Result should not exceed 32 bytes
    **/
    function delegateGet(address _target, string _signature, bytes32 _argument)
        internal returns (bytes32 result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _signature, 1, _argument, 0);
        assembly {
            result := mload(memoryAddress)
        }
    }

    /**
    * @dev Call "getter" with two parameters.
    * Result should not exceed 32 bytes
    **/
    function delegateGet(
        address _target,
        string _signature,
        bytes32 _argument1,
        bytes32 _argument2
    )
        internal returns (bytes32 result)
    {
        bytes32 memoryAddress = delegateGetData(_target, _signature, 2, _argument1, _argument2);
        assembly {
            result := mload(memoryAddress)
        }
    }
}
