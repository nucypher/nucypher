pragma solidity ^0.4.18;


/**
* @notice Contract for testing user escrow contract
**/
contract PolicyManagerForUserEscrowMock {

    function withdraw() public {
        require(address(this).balance > 0);
        msg.sender.transfer(address(this).balance);
    }

    function () public payable {}
}
