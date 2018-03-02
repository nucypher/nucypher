pragma solidity ^0.4.0;


import "contracts/MinersEscrow.sol";


/**
* @notice Contract for testing miners escrow contract
**/
contract PolicyManagerMock {

    MinersEscrow public escrow;
    mapping (address => uint256[]) public nodes;

    function PolicyManagerMock(address, MinersEscrow _escrow) public {
        escrow = _escrow;
    }

    /**
    * @notice Update node info
    **/
    function updateReward(address _node, uint256 _period) external {
        nodes[_node].push(_period);
    }

    /**
    * @notice Get length of array
    **/
    function getPeriodsLength(address _node) public view returns (uint256) {
        return nodes[_node].length;
    }

    /**
    * @notice Get period info
    **/
    function getPeriod(address _node, uint256 _index) public view returns (uint256) {
        return nodes[_node][_index];
    }

}
