pragma solidity ^0.4.18;


import "contracts/PolicyManager.sol";
import "contracts/MinersEscrow.sol";


/**
* @notice Contract for using in PolicyManager tests
**/
contract PolicyManagerBad is PolicyManager {

    constructor(MinersEscrow _escrow) public PolicyManager(_escrow) {
    }

    function getNodeInfo(PolicyManager.NodeInfoField, address, uint256)
        public view returns (bytes32)
    {
    }

}