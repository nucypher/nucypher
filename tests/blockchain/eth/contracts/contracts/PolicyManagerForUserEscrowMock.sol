pragma solidity ^0.4.24;


/**
* @notice Contract for testing user escrow contract
**/
contract PolicyManagerForUserEscrowMock {

    uint256 public minRewardRate;

    function withdraw(address _recipient) public returns (uint256) {
        uint256 value = address(this).balance;
        require(value > 0);
        _recipient.transfer(value);
        return value;
    }

    function setMinRewardRate(uint256 _minRewardRate) public {
        minRewardRate = _minRewardRate;
    }

    function () public payable {}
}
