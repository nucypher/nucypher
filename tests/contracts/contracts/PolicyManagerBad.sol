pragma solidity ^0.4.18;


import "contracts/PolicyManager.sol";
import "contracts/MinersEscrow.sol";


/**
* @notice Contract for using in PolicyManager tests
**/
contract PolicyManagerBad is PolicyManager {

    function PolicyManagerBad(MinersEscrow _escrow) public PolicyManager(_escrow) {
    }

    function getNodeInfoField(address, uint8, uint256)
        public view returns (bytes32)
    {
    }

}