pragma solidity ^0.4.24;


import "contracts/NuCypherToken.sol";


/**
* @notice Contract for using in UserEscrow tests
**/
contract MinersEscrowForUserEscrowMock {

    NuCypherToken token;
    address public node;
    uint256 public value;
    uint256 public lockedValue;
    uint16 public periods;
    uint16 public confirmedPeriod;
    uint256 public index;

    constructor(NuCypherToken _token) public {
        token = _token;
    }

    function deposit(uint256 _value, uint16 _periods) public {
        node = msg.sender;
        value = _value;
        lockedValue = _value;
        periods = _periods;
        token.transferFrom(msg.sender, address(this), _value);
    }

    function lock(uint256 _value, uint16 _periods) public {
        require(node == msg.sender);
        lockedValue += _value;
        periods += _periods;
    }

    function divideStake(uint256 _index, uint256 _newValue, uint16 _periods) public {
        require(node == msg.sender);
        index = _index;
        lockedValue += _newValue;
        periods += _periods;
    }

    function withdraw(uint256 _value) public {
        require(node == msg.sender);
        value -= _value;
        token.transfer(msg.sender, _value);
    }

    function withdrawAll() public {
        withdraw(value);
    }

    function confirmActivity() external {
        require(node == msg.sender);
        confirmedPeriod += 1;
    }

    function mint() external {
        require(node == msg.sender);
        value += 1000;
    }
}
