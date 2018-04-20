pragma solidity ^0.4.18;


import "contracts/NuCypherKMSToken.sol";


/**
* @notice Contract for using in UserEscrow tests
**/
contract MinersEscrowForUserEscrowMock {

    NuCypherKMSToken token;
    address public node;
    uint256 public value;
    uint256 public lockedValue;
    uint256 public periods;
    uint256 public confirmedPeriod;
    bool public unlock;

    constructor(NuCypherKMSToken _token) public {
        token = _token;
    }

    function deposit(uint256 _value, uint256 _periods) public {
        node = msg.sender;
        value = _value;
        lockedValue = _value;
        periods = _periods;
        unlock = false;
        token.transferFrom(msg.sender, address(this), _value);
    }

    function lock(uint256 _value, uint256 _periods) public {
        require(node == msg.sender);
        lockedValue += _value;
        periods += _periods;
    }

    function switchLock() public {
        require(node == msg.sender);
        unlock = !unlock;
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
