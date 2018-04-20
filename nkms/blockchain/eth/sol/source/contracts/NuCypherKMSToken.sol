pragma solidity ^0.4.23;


import "zeppelin/token/ERC20/BurnableToken.sol";
import "zeppelin/token/ERC20/StandardToken.sol";
import "zeppelin/token/ERC20/DetailedERC20.sol";


/**
* @title NuCypher KMS token
* @notice ERC20 token which can be burned by their owners
* @dev Optional approveAndCall() functionality to notify a contract if an approve() has occurred.
**/
contract NuCypherKMSToken is StandardToken, DetailedERC20('NuCypher KMS', 'KMS', 18), BurnableToken {

    /**
    * @notice Set amount of tokens
    * @param _initialAmount Initial amount of tokens
    **/
    constructor (uint256 _initialAmount) public {
        balances[msg.sender] = _initialAmount;
        totalSupply_ = _initialAmount;
        Transfer(0x0, msg.sender, _initialAmount);
    }

    /**
    * @notice Approves and then calls the receiving contract
    *
    * @dev call the receiveApproval function on the contract you want to be notified.
    * This crafts the function signature manually so one doesn't have to include a contract in here just for this.
    * receiveApproval(address _from, uint256 _value, address _tokenContract, bytes _extraData)
    * it is assumed that when does this that the call *should* succeed, otherwise one would use vanilla approve instead.
    **/
    function approveAndCall(address _spender, uint256 _value, bytes _extraData)
        public returns (bool success)
    {
        approve(_spender, _value);

        require(_spender.call(bytes4(keccak256("receiveApproval(address,uint256,address,bytes)")),
            msg.sender, _value, this, _extraData));
        return true;
    }

}
