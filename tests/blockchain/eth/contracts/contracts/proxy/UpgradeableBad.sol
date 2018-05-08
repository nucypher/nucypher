pragma solidity ^0.4.23;


import "proxy/Upgradeable.sol";


/**
* @notice Contract for testing government contract
**/
contract UpgradeableBad is Upgradeable {

    function verifyState(address) public {
        revert();
    }

    function finishUpgrade(address) public {}

}
