pragma solidity ^0.4.25;


import "contracts/UserEscrow.sol";
import "contracts/UserEscrowProxy.sol";
import "contracts/proxy/Upgradeable.sol";
import "contracts/proxy/Dispatcher.sol";
import "./Fixtures.sol";


/**
* @notice Tests that even owner can't upgrade without secret
**/
contract UserEscrowLibraryLinkerTest is UserEscrowLibraryLinker {

    constructor() public UserEscrowLibraryLinker(0x1, bytes32(1)) {
        owner = Fixtures.echidnaCaller();
    }

    function echidnaTargetTest() public view returns (bool) {
        return target == 0x1 && bytes32(1) == secretHash;
    }

}


contract UpgradeableImplementation is Upgradeable {

    function verifyState(address) public {
    }
    function finishUpgrade(address) public {
    }

}


/**
* @notice Tests that even owner can't upgrade without secret
**/
// TODO This test is not working because of error in `delegateCall` in echidna
contract DispatcherTest is Dispatcher {

    address initialTarget;

    constructor() public Dispatcher(new UpgradeableImplementation(), bytes32(1)) {
        owner = Fixtures.echidnaCaller();
        initialTarget = target;
    }

    function echidnaTargetTest() public view returns (bool) {
        return target == initialTarget && bytes32(1) == secretHash;
    }

}
