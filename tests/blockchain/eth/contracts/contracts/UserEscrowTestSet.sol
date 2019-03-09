pragma solidity ^0.5.3;


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
    bool public reStake;
    uint16 public lockReStakeUntilPeriod;

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
        lockedValue += _value;
        periods += _periods;
    }

    function divideStake(uint256 _index, uint256 _newValue, uint16 _periods) public {
        index = _index;
        lockedValue += _newValue;
        periods += _periods;
    }

    function withdraw(uint256 _value) public {
        value -= _value;
        token.transfer(msg.sender, _value);
    }

    function withdrawAll() public {
        withdraw(value);
    }

    function confirmActivity() external {
        confirmedPeriod += 1;
    }

    function mint() external {
        value += 1000;
    }

    function setReStake(bool _reStake) public {
        reStake = _reStake;
    }

    function lockReStake(uint16 _lockReStakeUntilPeriod) public {
        lockReStakeUntilPeriod = _lockReStakeUntilPeriod;
    }
}


/**
* @notice Contract for testing user escrow contract
**/
contract PolicyManagerForUserEscrowMock {

    uint256 public minRewardRate;

    function withdraw(address payable _recipient) public returns (uint256) {
        uint256 value = address(this).balance;
        require(value > 0);
        _recipient.transfer(value);
        return value;
    }

    function setMinRewardRate(uint256 _minRewardRate) public {
        minRewardRate = _minRewardRate;
    }

    function additionalMethod(uint256 _minRewardRate) public {
        minRewardRate = _minRewardRate;
    }

    function () external payable {}
}


/**
* @notice Contract for user escrow tests
**/
contract UserEscrowLibraryMockV1 {

    function firstMethod() public pure {}

    function secondMethod() public pure returns (uint256) {
        return 20;
    }

}


/**
* @notice Contract for user escrow tests
**/
contract UserEscrowLibraryMockV2 {

    function () external payable {
        // can only use with ETH
        require(msg.value > 0);
    }

    function firstMethod(uint256) public pure {}

    function secondMethod() public pure returns (uint256) {
        return 15;
    }

    function thirdMethod() public pure {}

}
