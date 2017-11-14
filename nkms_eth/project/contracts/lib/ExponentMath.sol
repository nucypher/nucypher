pragma solidity ^0.4.11;


/**
* @notice Math operations for calculating exponent
**/
library ExponentMath {

    /**
    * @notice Calculate k*e^(x/rate)
    * @param x Point on the curve
    * @param k Coefficient used for increase precision
    * @param rate Curve growing rate
    * @param iterations Calculate iterations. The higher the value,
    the greater the accuracy and the higher the cost
    * @return k*e^(x/rate)
    **/
    function exp(
        uint256 x,
        uint256 k,
        uint256 rate,
        uint64 iterations
    )
        internal constant returns (uint256)
    {
        require(iterations != 0);
        uint256 result = k + k * x / rate;
        uint256 factorial = 1;
        for (uint i = 2; i <= iterations; i++) {
            factorial *= i;
            uint256 value = k * (x ** i) / (factorial * (rate ** i));
            if (value == 0) {
                break;
            }
            result += value;
        }
        return result;
    }

    /**
    * @notice Calculate maxValue*(1-1/e^(x/rate))
    * @param x Point on the curve
    * @param maxValue Max value
    * @param rate Curve growing rate
    * @param multiplicator Coefficient used for increase precision.
    Low values lead to low accuracy, but high value can cause overflow
    * @param iterations Calculate iterations. The higher the value,
    the greater the accuracy and the higher the cost
    * @return maxValue*(1-1/e^(x/rate))
    **/
    function exponentialFunction(
        uint256 x,
        uint256 maxValue,
        uint256 rate,
        uint256 multiplicator,
        uint64 iterations
    )
        internal constant returns (uint256)
    {
        return (multiplicator * maxValue -
            maxValue * multiplicator ** 2 / exp(x, multiplicator, rate, iterations)) /
            multiplicator;
    }

}
