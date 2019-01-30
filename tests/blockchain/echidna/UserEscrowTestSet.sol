pragma solidity ^0.4.25;


import "./MasterContract.sol";
import "./Fixtures.sol";


contract UserEscrowTest1 is UserEscrowABI, UserEscrowProxyABI {

    address user = address(this);
    uint256 balance;

    constructor() public {
        build(0x0, 0x0, 0x0, 0x0);
        token.approve(userEscrow, 110000);
        userEscrow.initialDeposit(110000, 1000000);
        balance = token.balanceOf(user);
    }

    function echidnaLockedTokensTest() public view returns (bool) {
        return token.balanceOf(user) == balance;
    }

}


contract UserEscrowTest2 is UserEscrowABI, UserEscrowProxyABI {

    constructor() public {
        build(0x0, 0x0, 0x0, 0x0);
        token.approve(userEscrow, 100000);
        userEscrow.initialDeposit(100000, 1000000);
        userEscrow.transferOwnership(Fixtures.addressList(1));
    }

    function echidnaOwnershipTest() public view returns (bool) {
        return userEscrow.owner() == Fixtures.addressList(1);
    }

}
