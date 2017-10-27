pragma solidity ^0.4.8;


import "zeppelin-solidity/contracts/token/ERC20.sol";
import "./LinkedList.sol";


/**
* @notice Contract holds and locks client tokens.
Each client that lock his tokens will receive some compensation
**/
contract Escrow {
    using LinkedList for LinkedList.Data;

    struct TokenInfo {
        uint256 value;
        uint256 lockedValue;
        uint256 releaseBlock;
    }

    address owner;
    ERC20 token;
    mapping (address => TokenInfo) tokenInfo;
    LinkedList.Data tokenOwners;
    uint256 miningCoefficient;

    /**
    * @dev Throws if called by any account other than the _user.
    * @param _user The user who is allowed to call
    **/
    modifier onlyBy(address _user) {
        require(msg.sender == _user);
        _;
    }

    /**
    * @dev Throws if not locked tokens less then _value.
    * @param _owner Owner of tokens
    * @param _value Amount of tokens to check
    **/
    modifier whenNotLocked(address _owner, uint256 _value) {
        require(_value <= token.balanceOf(address(this)));
        require(_value <= tokenInfo[_owner].value - getLockedTokens(_owner));
        _;
    }

    /**
    * @notice The Escrow constructor sets address of token contract and mining coefficient
    * @param _token Token contract
    * @param _miningCoefficient amount of tokens that will be credited
    for each locked token in each iteration
    **/
    function Escrow(ERC20 _token, uint256 _miningCoefficient) {
        token = _token;
        owner = msg.sender;
        miningCoefficient = _miningCoefficient;
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
        if (!token.transferFrom(msg.sender, address(this), _value)) {
            revert();
            return false;
        }
        return true;
    }

    /**
    * @notice Lock some tokens
    * @param _value Amount of tokens which should lock
    * @param _releaseBlock Block number when tokens will be unlocked
    **/
    function lock(uint256 _value, uint256 _releaseBlock) returns (bool success) {
        require(_value <= tokenInfo[msg.sender].value && _releaseBlock > 0);
        require(_value <= token.balanceOf(address(this)));
        require(getLockedTokens(msg.sender) == 0);
        tokenInfo[msg.sender].lockedValue = _value;
        tokenInfo[msg.sender].releaseBlock = _releaseBlock;
        return true;
    }

    /**
    * @notice Withdraw available amount of tokens back to owner
    * @param _value Amount of token to withdraw
    **/
    function withdraw(uint256 _value)
        whenNotLocked(msg.sender, _value)
        returns (bool success)
    {
        tokenInfo[msg.sender].value -= _value;
        if (!token.transfer(msg.sender, _value)) {
            revert();
            return false;
        }
        return true;
    }

    /**
    * @notice Withdraw all amount of tokens back to owner (only if no locked)
    **/
    function withdrawAll()
        whenNotLocked(msg.sender, tokenInfo[msg.sender].value)
        returns (bool success)
    {
        if (!tokenOwners.valueExists(msg.sender)) {
            return true;
        }
        tokenOwners.remove(msg.sender);
        uint256 value = tokenInfo[msg.sender].value;
        delete tokenInfo[msg.sender];
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
    **/
    function destroy() onlyBy(owner) public {
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

    /**
    * @notice Get locked tokens value in a specified moment in time
    * @param _owner Tokens owner
    * @param _blockNumber Block number for checking
    **/
    function getLockedTokens(address _owner, uint256 _blockNumber)
        public constant returns (uint256)
    {
        if (tokenInfo[_owner].releaseBlock <= _blockNumber) {
            return 0;
        } else {
            return tokenInfo[_owner].lockedValue;
        }
    }

    /**
    * @notice Get locked tokens value for all owners in a specified moment in time
    * @param _blockNumber Block number for checking
    **/
    function getAllLockedTokens(uint256 _blockNumber)
        public constant returns (uint256 result)
    {
        var current = tokenOwners.step(0x0, true);
        while (current != 0x0) {
            result += getLockedTokens(current, _blockNumber);
            current = tokenOwners.step(current, true);
        }
    }

    /**
    * @notice Get locked tokens value for owner
    * @param _owner Tokens owner
    **/
    function getLockedTokens(address _owner)
        public constant returns (uint256)
    {
        return getLockedTokens(_owner, block.number);
    }

    /**
    * @notice Get locked tokens value for all owners
    **/
    function getAllLockedTokens()
        public constant returns (uint256 result)
    {
        return getAllLockedTokens(block.number);
    }

    /**
    * @notice Mine tokens for all users who locked their tokens
    **/
    function mine() onlyBy(owner) {
        var current = tokenOwners.step(0x0, true);
        while (current != 0x0) {
            var lockedValue = getLockedTokens(current);
            if (lockedValue > 0) {
                //TODO handle overflow
                tokenInfo[current].value += lockedValue * miningCoefficient;
            }
            current = tokenOwners.step(current, true);
        }
    }
}
