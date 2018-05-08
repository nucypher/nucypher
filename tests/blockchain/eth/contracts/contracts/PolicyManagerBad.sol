pragma solidity ^0.4.23;


import "contracts/PolicyManager.sol";
import "contracts/MinersEscrow.sol";


/**
* @notice Contract for using in PolicyManager tests
**/
contract PolicyManagerBad is PolicyManager {

    constructor(MinersEscrow _escrow) public PolicyManager(_escrow) {
    }

    function getNodeRewardDelta(address _node, uint256 _period)
        public view returns (int256)
    {
    }

}