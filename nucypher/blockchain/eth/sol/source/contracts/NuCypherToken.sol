pragma solidity ^0.5.3;


import "zeppelin/token/ERC20/ERC20.sol";
import "zeppelin/token/ERC20/ERC20Detailed.sol";


/**
* @title NuCypher token
* @notice ERC20 token
* @dev Optional approveAndCall() functionality to notify a contract if an approve() has occurred.
**/
contract NuCypherToken is ERC20, ERC20Detailed('NuCypher', 'NU', 18) {

    /**
    * @notice Set amount of tokens
    * @param _totalSupply Total number of tokens
    **/
    constructor (uint256 _totalSupply) public {
        _mint(msg.sender, _totalSupply);
    }

    /**
    * @notice Approves and then calls the receiving contract
    *
    * @dev call the receiveApproval function on the contract you want to be notified.
    * receiveApproval(address _from, uint256 _value, address _tokenContract, bytes _extraData)
    **/
    function approveAndCall(address _spender, uint256 _value, bytes memory _extraData)
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
    function receiveApproval(address _from, uint256 _value, address _tokenContract, bytes calldata _extraData) external;

}
