pragma solidity ^0.4.24;


/**
* @notice Contract for testing user escrow contract
**/
contract PolicyManagerForUserEscrowMock {

    uint256 public minRewardRate;

    function withdraw() public {
        require(address(this).balance > 0);
        msg.sender.transfer(address(this).balance);
    }

    function setMinRewardRate(uint256 _minRewardRate) public {
        minRewardRate = _minRewardRate;
    }

    function () public payable {}
}
