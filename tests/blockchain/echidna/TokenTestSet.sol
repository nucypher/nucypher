pragma solidity ^0.5.3;


import "contracts/NuCypherToken.sol";
import "./Fixtures.sol";


/**
* @notice Tests that caller can transfer only approved tokens
**/
contract TokenTest1 is NuCypherToken {

    constructor() public NuCypherToken(0) {
        _mint(Fixtures.addressList(1), 1000);
        _mint(Fixtures.addressList(2), 1000);
        _approve(Fixtures.addressList(2), Fixtures.echidnaCaller(), 500);
    }

    function echidnaOwningTest1() public view returns (bool) {
        return balanceOf(Fixtures.addressList(1)) >= 1000 &&
            balanceOf(Fixtures.addressList(1)) <= 1500;
    }

    function echidnaOwningTest2() public view returns (bool) {
        return balanceOf(Fixtures.addressList(2)) <= 1000 &&
            balanceOf(Fixtures.addressList(2)) >= 500;
    }

}


/**
* @notice Tests that caller can't just get tokens from nowhere
**/
contract TokenTest2 is NuCypherToken {

    constructor() public NuCypherToken(0) {
        _mint(Fixtures.echidnaCaller(), 1000);
    }

    function echidnaBalanceTest() public view returns (bool) {
        return balanceOf(Fixtures.echidnaCaller()) <= 1000;
    }

}
