pragma solidity ^0.4.18;


import "zeppelin/ownership/Ownable.sol";


/**
* @notice Base contract for upgradeable contract
* @dev Implementation contract should realize verifyState(address testTarget) method
* by checking storage variables (see verifyState(address testTarget) in Dispatcher)
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
    * @dev Simple method for call function without parameters.
    * Result should not exceed 32 bytes
    **/
    //TODO fix return size
    function delegateGet(address _testTarget, string _signature)
        internal returns (bytes32 result)
    {
        bytes4 targetCall = bytes4(keccak256(_signature));
        assembly {
            let free := mload(0x40)
            mstore(free, targetCall)
            let retVal := delegatecall(gas, _testTarget, free, 4, free, 32)
            result := mload(free)
        }
    }

    /**
    * @dev Simple method for call function with one parameter.
    * Result should not exceed 32 bytes
    **/
    //TODO fix return size
    function delegateGet(address _testTarget, string _signature, bytes32 _argument)
        internal returns (bytes32 result)
    {
        bytes4 targetCall = bytes4(keccak256(_signature));
        assembly {
            let in_pos := mload(0x40)
            mstore(in_pos, targetCall)
            mstore(add(in_pos, 0x04), _argument)
            switch delegatecall(gas, _testTarget, in_pos, 0x24, in_pos, 32)
                case 0 {
                    revert(0x0, 0)
                }
                default {
                   result := mload(in_pos)
                   mstore(0x40, add(in_pos, 0x24))
                }
        }
    }

    /**
    * @dev Simple method for call function with two parameters.
    * Result should not exceed 32 bytes
    **/
    //TODO fix return size
    function delegateGet(
        address _testTarget,
        string _signature,
        bytes32 _argument1,
        bytes32 _argument2
    )
        internal returns (bytes32 result)
    {
        bytes4 targetCall = bytes4(keccak256(_signature));
        assembly {
            let in_pos := mload(0x40)
            mstore(in_pos, targetCall)
            mstore(add(in_pos, 0x04), _argument1)
            mstore(add(in_pos, 0x24), _argument2)
            switch delegatecall(gas, _testTarget, in_pos, 0x44, in_pos, 32)
                case 0 {
                    revert(0x0, 0)
                }
                default {
                   result := mload(in_pos)
                   mstore(0x40, add(in_pos, 0x44))
                }
        }
    }

    /**
    * @dev Simple method for call function with three parameters.
    * Result should not exceed 32 bytes
    **/
    //TODO fix return size
    function delegateGet(
        address _testTarget,
        string _signature,
        bytes32 _argument1,
        bytes32 _argument2,
        bytes32 _argument3
    )
        internal returns (bytes32 result)
    {
        bytes4 targetCall = bytes4(keccak256(_signature));
        assembly {
            let in_pos := mload(0x40)
            mstore(in_pos, targetCall)
            mstore(add(in_pos, 0x04), _argument1)
            mstore(add(in_pos, 0x24), _argument2)
            mstore(add(in_pos, 0x44), _argument3)
            switch delegatecall(gas, _testTarget, in_pos, 0x64, in_pos, 32)
                case 0 {
                    revert(0x0, 0)
                }
                default {
                   result := mload(in_pos)
                   mstore(0x40, add(in_pos, 0x64))
                }
        }
    }
}
