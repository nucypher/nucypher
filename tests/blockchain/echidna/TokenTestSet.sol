pragma solidity ^0.4.25;


import "contracts/NuCypherToken.sol";
import "./Constants.sol";


contract TokenTest1 is NuCypherToken, Constants {

    constructor() public NuCypherToken(0) {
        balances[Constants.ADDRESS_1] = 1000;
        balances[Constants.ADDRESS_2] = 1000;
        allowed[Constants.ADDRESS_2][Constants.ECHIDNA_CALLER] = 500;
        totalSupply_ = 2000;
    }

    function echidnaOwningTest1() public view returns (bool) {
        return balances[Constants.ADDRESS_1] >= 1000 &&
            balances[Constants.ADDRESS_1] <= 1500;
    }

    function echidnaOwningTest2() public view returns (bool) {
        return balances[Constants.ADDRESS_2] <= 1000 &&
            balances[Constants.ADDRESS_2] >= 500;
    }

}


contract TokenTest2 is NuCypherToken, Constants {

    constructor() public NuCypherToken(0) {
        balances[Constants.ECHIDNA_CALLER] = 1000;
        totalSupply_ = 1000;
    }

    function echidnaBalanceTest() public view returns (bool) {
        return balances[Constants.ECHIDNA_CALLER] <= 1000;
    }

}
