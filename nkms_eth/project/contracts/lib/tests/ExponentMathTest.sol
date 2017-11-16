pragma solidity ^0.4.11;


import "../ExponentMath.sol";


/**
* @dev Contract for testing ExponentMath library
**/
contract ExponentMathTest {

    /**
    * @dev maxValue*(1-1/e^(x/rate))
    **/
    function exponentialFunction(
        uint256 x,
        uint256 maxValue,
        uint256 rate,
        uint256 multiplicator,
        uint64 iterations
    )
        constant returns (uint256)
    {
        return ExponentMath.exponentialFunction(x, maxValue, rate, multiplicator, iterations);
    }

    /**
    * @dev k*e^(x/rate)
    **/
    function exp(
        uint256 x,
        uint256 k,
        uint256 rate,
        uint64 iterations
    )
        constant returns (uint256)
    {
        return ExponentMath.exp(x, k, rate, iterations);
    }

}
