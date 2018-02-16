pragma solidity ^0.4.18;


import "contracts/proxy/Upgradeable.sol";


/**
* @notice Contract for testing government contract
**/
contract PolicyManagerV1Test is Upgradeable {

    function PolicyManagerV1Test() {

    }

    function verifyState(address testTarget) public constant {

    }

    function finishUpgrade(address _target) onlyOwner public {

    }

}
