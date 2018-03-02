pragma solidity ^0.4.0;


import "contracts/lib/LinkedList.sol";


/**
* @notice Contract for testing LinkedList library
* @dev see https://github.com/Majoolr/ethereum-libraries/blob/master/LinkedListLib/truffle/contracts/LinkedListTestContract.sol
**/
contract LinkedListMock {
    using LinkedList for LinkedList.Data;

    LinkedList.Data list;

    function exists() public view returns (bool) {
        return list.exists();
    }

    function valueExists(address _value) public view returns (bool) {
        return list.valueExists(_value);
    }

    function sizeOf() public view returns (uint256 numElements) {
        return list.sizeOf();
    }

    function getLinks(address _value) public view returns (address[2]) {
        return list.getLinks(_value);
    }

    function step(address _value, bool _direction) public view returns (address) {
        return list.step(_value, _direction);
    }

    function createLinks(address _node, address _link, bool _direction) public {
        list.createLinks(_node,_link,_direction);
    }

    function insert(address _node, address _new, bool _direction) public {
        list.insert(_node,_new,_direction);
    }

    function remove(address _node) public returns (address) {
        return list.remove(_node);
    }

    function push(address _node, bool _direction) public {
        list.push(_node,_direction);
    }

    function pop(bool _direction) public returns (address) {
        return list.pop(_direction);
    }

}
