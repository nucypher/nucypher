pragma solidity ^0.4.23;

/**
* @notice Doubly linked list for addresses
* @dev see https://github.com/o0ragman0o/LibCLL
* @dev see https://github.com/Majoolr/ethereum-libraries/blob/master/LinkedListLib/truffle/contracts/LinkedListLib.sol
**/
library LinkedList {

    address constant NULL = 0x0;
    address constant HEAD = NULL;
    bool constant PREV = false;
    bool constant NEXT = true;

    struct Data {
        mapping (address => mapping (bool => address)) data;
        uint256 count;
    }

    /// @notice Return existential state of a list.
    function exists(Data storage self)
        internal view returns (bool)
    {
        if (self.data[HEAD][PREV] != HEAD ||
            self.data[HEAD][NEXT] != HEAD)
            return true;
    }

    /// @notice Returns the number of elements in the list
    function sizeOf(Data storage self)
        internal view returns (uint result)
    {
        return self.count;
    }

    /**
    * @notice Check existence of a value
    * @param value Value to search for
    **/
    function valueExists(Data storage self, address value)
        internal view returns (bool)
    {
        if (self.data[value][PREV] == HEAD && self.data[value][NEXT] == HEAD) {
            if (self.data[HEAD][NEXT] == value) {
                return true;
            } else {
                return false;
            }
        } else {
            return true;
        }
    }

    /// @notice Returns the links of a value as an array
    function getLinks(Data storage self, address value)
        internal view returns (address[2])
    {
        return [self.data[value][PREV], self.data[value][NEXT]];
    }

    /// @notice Returns the link of a value in specified direction.
    function step(Data storage self, address value, bool direction)
        internal view returns (address)
    {
        return self.data[value][direction];
    }

    /// @notice Creates a bidirectional link between two nodes on specified direction
    function createLinks(
        Data storage self,
        address from,
        address to,
        bool direction
    )
        internal
    {
        self.data[to][!direction] = from;
        self.data[from][direction] = to;
    }

    /// @notice Insert value beside existing value `from` in specified direction.
    function insert (
        Data storage self,
        address from,
        address value,
        bool direction
    )
        internal
    {
        address to = self.data[from][direction];
        createLinks(self, from, value, direction);
        createLinks(self, value, to, direction);
        self.count++;
    }

    /// @notice Remove value from the list.
    function remove(Data storage self, address value) internal returns (address) {
        if (value == NULL ||
            ((self.data[value][NEXT] == HEAD) &&
            (self.data[value][PREV] == HEAD) &&
            (self.data[self.data[value][PREV]][NEXT] != value))) {
            return NULL;
        }
        createLinks(self, self.data[value][PREV], self.data[value][NEXT], NEXT);
        delete self.data[value][PREV];
        delete self.data[value][NEXT];
        self.count--;
        return value;
    }

    /// @notice Put value to the top of the list in specified direction.
    function push(Data storage self, address value, bool direction) internal  {
        insert(self, HEAD, value, direction);
    }

    /// @notice Get value from the top of the list in specified direction and remove it.
    function pop(Data storage self, bool direction) internal returns (address) {
        return remove(self, step(self, HEAD, direction));
    }
}
