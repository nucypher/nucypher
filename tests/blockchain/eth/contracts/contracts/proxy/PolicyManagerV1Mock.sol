pragma solidity ^0.4.23;


import "proxy/Upgradeable.sol";


/**
* @notice Contract for testing government contract
**/
contract PolicyManagerV1Mock is Upgradeable {

    function verifyState(address) public {}
    function finishUpgrade(address) public {}

    function setPreviousTarget(address _target) public {
        previousTarget = _target;
    }
}
