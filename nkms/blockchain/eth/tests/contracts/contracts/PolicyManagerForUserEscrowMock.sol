pragma solidity ^0.4.18;


/**
* @notice Contract for testing user escrow contract
**/
contract PolicyManagerForUserEscrowMock {

    function withdraw() public {
        require(this.balance > 0);
        msg.sender.transfer(this.balance);
    }

    function () public payable {}
}
