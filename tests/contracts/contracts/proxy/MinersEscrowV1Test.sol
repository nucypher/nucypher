pragma solidity ^0.4.18;


import "contracts/proxy/Upgradeable.sol";


/**
* @notice Contract for using in Government tests
**/
contract MinersEscrowV1Test is Upgradeable {

    mapping (address => uint256) public lockedTokens;
    address[] public nodes;

    /**
    * @param _nodes Addresses of nodes
    * @param _lockedTokens Locked tokens for nodes
    **/
    function MinersEscrowV1Test(address[] _nodes, uint256[] _lockedTokens) {
        for (uint256 i = 0; i < _nodes.length ; i++) {
            lockedTokens[_nodes[i]] = _lockedTokens[i];
        }
    }

    function getLockedTokens(address _owner)
        public constant returns (uint256)
    {
        return lockedTokens[_owner];
    }

    function getNodesLength() public constant returns (uint256) {
        return nodes.length;
    }

    function verifyState(address testTarget) public constant {

    }

    function finishUpgrade(address _target) onlyOwner public {
        var escrow = MinersEscrowV1Test(_target);
        for (uint256 i = 0; i < escrow.getNodesLength(); i++) {
            var node = escrow.nodes(i);
            nodes.push(node);
            lockedTokens[node] = escrow.lockedTokens(node);
        }
    }
}
