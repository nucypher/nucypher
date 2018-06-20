pragma solidity ^0.4.24;


/**
* @notice Contract for testing user escrow contract
**/
contract GovernmentForUserEscrowMock {

    bool public voteFor;

    function vote(bool _voteFor) public {
        voteFor = _voteFor;
    }

}
