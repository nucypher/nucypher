pragma solidity ^0.4.24;


import "contracts/PolicyManager.sol";
import "contracts/MinersEscrow.sol";


/**
* @notice Contract for using in PolicyManager tests
**/
contract PolicyManagerBad is PolicyManager {

    constructor(MinersEscrow _escrow) public PolicyManager(_escrow) {
    }

    function getNodeRewardDelta(address, uint16) public view returns (int256)
    {
    }

}