pragma solidity ^0.5.3;


import "./MasterContract.sol";
import "./Fixtures.sol";


/**
* @notice Tests that owner can't get tokens before cliff
**/
// TODO This test is not working (but running) because of error in `delegateCall` in echidna
contract UserEscrowTest1 is UserEscrowABI, UserEscrowProxyABI {

    address user = address(this);
    uint256 balance;

    constructor() public {
        build(address(0), address(0), address(0), address(0));
        token.approve(address(userEscrow), 110000);
        userEscrow.initialDeposit(110000, 1000000);
        balance = token.balanceOf(user);
    }

    function echidnaLockedTokensTest() public view returns (bool) {
        return token.balanceOf(user) == balance;
    }

}


/**
* @notice Tests that nobody can get ownership of the UserEscrow contract
**/
contract UserEscrowTest2 is UserEscrowABI, UserEscrowProxyABI {

    constructor() public {
        build(address(0), address(0), address(0), address(0));
        token.approve(address(userEscrow), 100000);
        userEscrow.initialDeposit(100000, 1000000);
        userEscrow.transferOwnership(Fixtures.addressList(1));
    }

    function echidnaOwnershipTest() public view returns (bool) {
        return userEscrow.owner() == Fixtures.addressList(1);
    }

}
