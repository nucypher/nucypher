pragma solidity ^0.4.23;


import "zeppelin/math/SafeMath.sol";


/**
* @notice Additional math operations
**/
library AdditionalMath {
    using SafeMath for uint256;

    /**
    * @notice Division and ceil
    **/
    function divCeil(uint256 a, uint256 b) internal pure returns (uint256) {
        return (a.add(b) - 1) / b;
    }

    /**
    * @dev Adds unsigned value to signed value, throws on overflow.
    */
    function add(int256 a, uint256 b) internal pure returns (int256) {
        int256 c = a + int256(b);
        assert(c >= a);
        return c;
    }

    /**
    * @dev Subtracts two numbers, throws on overflow.
    */
    function sub(int256 a, uint256 b) internal pure returns (int256) {
        int256 c = a - int256(b);
        assert(c <= a);
        return c;
    }

    /**
    * @dev Adds signed value to unsigned value, throws on overflow.
    */
    function add(uint256 a, int256 b) internal pure returns (uint256) {
        if (b >= 0) {
            return a.add(uint256(b));
        } else {
            return a.sub(uint256(-b));
        }
    }

    /**
    * @dev Subtracts signed value from unsigned value, throws on overflow.
    */
    function sub(uint256 a, int256 b) internal pure returns (uint256) {
        if (b >= 0) {
            return a.sub(uint256(b));
        } else {
            return a.add(uint256(-b));
        }
    }

}
