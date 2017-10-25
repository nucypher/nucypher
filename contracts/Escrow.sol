pragma solidity ^0.4.8;


import "./Token.sol";
import "./LinkedList.sol";


/*
   This contract holds money and is being controlled by the Jury contract
   This contract is a multi-personal "multisig wallet".
   If someone else deposits to this wallet, this will be considered a donation to owner :-P
*/
contract Escrow {
    using LinkedList for LinkedList.Data;

    struct TokenInfo {
        uint256 value;
        uint256 lockedValue;
    }

    address owner;
    address tokenContractAddress;
    address jury;
    mapping (address => TokenInfo) tokenInfo;
    LinkedList.Data tokenOwners;

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
    * @notice The Escrow constructor sets address of token contract and jury address
    * @param _tokenContractAddress Token contract address
    * @param _jury The user who is allowed to locking token
    **/
    function Escrow(address _tokenContractAddress, address _jury) {
        tokenContractAddress = _tokenContractAddress;
        jury = _jury;
        owner = msg.sender;
    }

    /**
    * @notice Setting locked value. Available only for jury
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
    * @notice Withdraw available amount of tokens back to owner
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
    * @notice Deposit tokens
    * @param _value Amount of token to deposit
    **/
    function deposit(uint256 _value) returns (bool success) {
        if (!tokenOwners.valueExists(msg.sender)) {
            tokenOwners.push(msg.sender, true);
        }
        tokenInfo[msg.sender].value += _value;
        Token token = Token(tokenContractAddress);
        if (!token.transferFrom(msg.sender, address(this), _value)) {
            revert();
            return false;
        }
        return true;
    }

    /**
    * @notice Withdraw all amount of tokens back to owner (only if no locked)
    **/
    function withdrawAll() returns (bool success) {
        require(tokenInfo[msg.sender].lockedValue == 0);
        if (!tokenOwners.valueExists(msg.sender)) {
            return true;
        }
        tokenOwners.remove(msg.sender);
        uint256 value = tokenInfo[msg.sender].value;
        delete tokenInfo[msg.sender];
        Token token = Token(tokenContractAddress);
        if (!token.transfer(msg.sender, value)) {
            revert();
            return false;
        }
        return true;
    }

    /**
    * @notice Terminate contract and refund to owners
    * @dev The called token contracts could try to re-enter this contract.
    Only supply token contracts you trust.
    */
    function destroy() onlyBy(owner) public {
        Token token = Token(tokenContractAddress);

        // Transfer tokens to owners
        var current = tokenOwners.step(0x0, true);
        while (current != 0x0) {
            //TODO handle errors
            token.transfer(current, tokenInfo[current].value);
            current = tokenOwners.step(current, true);
        }
        //TODO handle errors
        token.transfer(owner, token.balanceOf(address(this)));

        // Transfer Eth to owner and terminate contract
        selfdestruct(owner);
    }

//    /**
//    * @notice Withdraw tokens to owner
//    * @param _to Owner of tokens
//    * @param _value Amount of token to withdraw
//    **/
//    function withdrawTo(address _to, uint256 _value) internal returns (bool success) {
//        tokenInfo[_to].value -= _value;
//        Token token = Token(tokenContractAddress);
//        return token.transfer(_to, _value);
//    }

}
