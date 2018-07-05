pragma solidity ^0.4.24;


import "zeppelin/token/ERC20/BurnableToken.sol";
import "zeppelin/token/ERC20/StandardToken.sol";
import "zeppelin/token/ERC20/DetailedERC20.sol";


/**
* @title NuCypher token
* @notice ERC20 token which can be burned by their owners
* @dev Optional approveAndCall() functionality to notify a contract if an approve() has occurred.
**/
contract NuCypherToken is StandardToken, DetailedERC20('NuCypher', 'NU', 18), BurnableToken {

    /**
    * @notice Set amount of tokens
    * @param _initialAmount Initial amount of tokens
    **/
    constructor (uint256 _initialAmount) public {
        balances[msg.sender] = _initialAmount;
        totalSupply_ = _initialAmount;
        emit Transfer(0x0, msg.sender, _initialAmount);
    }

    /**
    * @notice Approves and then calls the receiving contract
    *
    * @dev call the receiveApproval function on the contract you want to be notified.
    * receiveApproval(address _from, uint256 _value, address _tokenContract, bytes _extraData)
    **/
    function approveAndCall(address _spender, uint256 _value, bytes _extraData)
        public returns (bool success)
    {
        approve(_spender, _value);
        TokenRecipient(_spender).receiveApproval(msg.sender, _value, address(this), _extraData);
        return true;
    }

}


/**
* @dev Interface to use the receiveApproval method
**/
contract TokenRecipient {

    /**
    * @notice Receives a notification of approval of the transfer
    * @param _from Sender of approval
    * @param _value  The amount of tokens to be spent
    * @param _tokenContract Address of the token contract
    * @param _extraData Extra data
    **/
    function receiveApproval(address _from, uint256 _value, address _tokenContract, bytes _extraData) external;

}
