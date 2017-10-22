pragma solidity ^0.4.8;
import "./Token.sol";

/*
   This contract holds money and is being controlled by the Jury contract
   This contract is a multi-personal "multisig wallet".
   If someone else deposits to this wallet, this will be considered a donation :-P
*/
contract Escrow {

    struct TokenInfo {
        address owner;
        uint256 value;
        uint256 lockedValue;
    }

    address tokenContractAddress;
    address jury;
    mapping (address => TokenInfo) tokenInfo;

    /**
    * @dev Throws if called by any account other than the _user.
    * @param _user The user who is allowed to call
    **/
    modifier onlyBy(address _user) {
        require(msg.sender == _user);
        _;
    }

    /**
    * @dev Throws if tokens less then _value.
    * @param _owner Owner of tokens
    * @param _value Amount of tokens to check
    **/
    modifier whenAvailable(address _owner, uint256 _value) {
        Token token = Token(tokenContractAddress);
        require(_value <= token.balanceOf(address(this)));
        require(_value <= tokenInfo[_owner].value);
        _;
    }

    /**
    * @dev The Escrow constructor sets address of token contract and jury address
    * @param _tokenContractAddress Token contract address
    * @param _jury The user who is allowed to locking token
    **/
    function Escrow(address _tokenContractAddress, address _jury) {
        tokenContractAddress = _tokenContractAddress;
        jury = _jury;
    }

    /**
    * @dev Setting locked value. Available only for jury
    * @param _owner Owner of tokens
    * @param _value Amount of tokens which should lock
    **/
    function setLock(address _owner, uint256 _value)
        onlyBy(jury)
        whenAvailable(_owner, _value)
        returns (bool success)
    {
        tokenInfo[_owner].lockedValue = _value;
        return true;
    }

    /**
    * @dev Withdraw available amount of tokens back to owner
    * @param _value Amount of token to withdraw
    **/
    function withdraw(uint256 _value)
        whenAvailable(msg.sender, _value + tokenInfo[msg.sender].lockedValue)
        returns (bool success)
    {
        tokenInfo[msg.sender].value -= _value;
        Token token = Token(tokenContractAddress);
        if (!token.transfer(msg.sender, _value)) {
            revert();
            return false;
        }
        return true;
    }

    /**
    * @dev Deposit tokens
    * @param _value Amount of token to deposit
    **/
    function deposit(uint256 _value) returns (bool success) {
        tokenInfo[msg.sender].value += _value;
        Token token = Token(tokenContractAddress);
        if (!token.transferFrom(msg.sender, address(this), _value)) {
            revert();
            return false;
        }
        return true;
    }

}
