pragma solidity ^0.4.18;


import "proxy/Upgradeable.sol";


/**
* @notice Contract for using in Government tests
**/
contract MinersEscrowV1Mock is Upgradeable {

    mapping (address => uint256) public lockedTokens;
    address[] public nodes;

    /**
    * @param _nodes Addresses of nodes
    * @param _lockedTokens Locked tokens for nodes
    **/
    constructor(address[] _nodes, uint256[] _lockedTokens) public {
        for (uint256 i = 0; i < _nodes.length ; i++) {
            lockedTokens[_nodes[i]] = _lockedTokens[i];
        }
        nodes = _nodes;
    }

    function getLockedTokens(address _owner)
        public view returns (uint256)
    {
        return lockedTokens[_owner];
    }

    function getNodesLength() public view returns (uint256) {
        return nodes.length;
    }

    function verifyState(address) public {}

    function finishUpgrade(address _target) public onlyOwner {
        MinersEscrowV1Mock escrow = MinersEscrowV1Mock(_target);
        for (uint256 i = 0; i < escrow.getNodesLength(); i++) {
            address node = escrow.nodes(i);
            nodes.push(node);
            lockedTokens[node] = escrow.lockedTokens(node);
        }
    }
}
