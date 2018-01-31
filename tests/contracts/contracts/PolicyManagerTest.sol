pragma solidity ^0.4.0;


import "contracts/Escrow.sol";


/**
* @notice Contract for testing Escrow contract
**/
contract PolicyManagerTest {

    Escrow public escrow;
    mapping (address => uint256[]) public nodes;

    function PolicyManagerTest(address _token, Escrow _escrow) {
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
    function getPeriodsLength(address _node) public constant returns (uint256) {
        return nodes[_node].length;
    }

    /**
    * @notice Get period info
    **/
    function getPeriod(address _node, uint256 _index) public constant returns (uint256) {
        return nodes[_node][_index];
    }

}
