pragma solidity ^0.4.18;


import "../zeppelin/math/SafeMath.sol";


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

}
