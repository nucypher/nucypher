pragma solidity ^0.4.18;


import "proxy/Upgradeable.sol";


/**
* @notice Contract for testing government contract
**/
contract PolicyManagerV1Mock is Upgradeable {

    constructor() public {}
    function verifyState(address) public {}
    function finishUpgrade(address) public {}

}
