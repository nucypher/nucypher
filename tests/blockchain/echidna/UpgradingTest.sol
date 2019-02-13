pragma solidity ^0.5.3;


import "contracts/UserEscrow.sol";
import "contracts/UserEscrowProxy.sol";
import "contracts/proxy/Upgradeable.sol";
import "contracts/proxy/Dispatcher.sol";
import "./Fixtures.sol";


/**
* @notice Tests that even owner can't upgrade without secret
**/
contract UserEscrowLibraryLinkerTest is UserEscrowLibraryLinker {

    constructor() public UserEscrowLibraryLinker(address(1), bytes32(uint256(1))) {
        transferOwnership(Fixtures.echidnaCaller());
    }

    function echidnaTargetTest() public view returns (bool) {
        return target == address(1) && bytes32(uint256(1)) == secretHash;
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

    constructor() public Dispatcher(address(new UpgradeableImplementation()), bytes32(uint256(1))) {
        transferOwnership(Fixtures.echidnaCaller());
        initialTarget = target;
    }

    function echidnaTargetTest() public view returns (bool) {
        return target == initialTarget && bytes32(uint256(1)) == secretHash;
    }

}
