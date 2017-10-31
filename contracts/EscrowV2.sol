pragma solidity ^0.4.8;


import "zeppelin-solidity/contracts/token/ERC20.sol";
import "zeppelin-solidity/contracts/ownership/Ownable.sol";
import "./LinkedList.sol";

/**
* @notice Contract holds and locks client tokens.
**/
contract Wallet is Ownable {

    ERC20 token;
    uint256 public lockedValue;
    uint256 public lockedBlock;
    uint256 public releaseBlock;
    uint256 public decimals;
    address manager;

    /**
    * @dev Throws if called by any account other than the _user.
    * @param _user The user who is allowed to call
    **/
    modifier onlyBy(address _user) {
        require(msg.sender == _user);
        _;
    }

    /**
    * @notice Wallet constructor set token contract
    * @param _token Token contract
    **/
    function Wallet(ERC20 _token) {
        token = _token;
//        manager = WalletManager(msg.sender);
        manager = msg.sender;
    }

    /**
    * @notice Lock some tokens
    * @param _value Amount of tokens which should lock
    * @param _blocks Amount of blocks during which tokens will be locked
    **/
    function lock(uint256 _value, uint256 _blocks)
//        onlyBy(manager)
        onlyOwner
        returns (bool success)
    {
        require(_value <= token.balanceOf(address(this)) && _blocks > 0);
        require(getLockedTokens() == 0);
        lockedValue = _value;
        releaseBlock = block.number + _blocks;
        lockedBlock = block.number;
        return true;
    }

    /**
    * @notice Withdraw available amount of tokens back to owner
    * @param _value Amount of token to withdraw
    **/
    function withdraw(uint256 _value) onlyOwner returns (bool success) {
        require(_value <= token.balanceOf(address(this)) - getLockedTokens());
        return token.transfer(msg.sender, _value);
    }

    /**
    * @notice Get locked tokens value in a specified moment in time
    * @param _blockNumber Block number for checking
    **/
    function getLockedTokens(uint256 _blockNumber)
        public constant returns (uint256)
    {
        if (releaseBlock <= _blockNumber) {
            return 0;
        } else {
            return lockedValue;
        }
    }

    /**
    * @notice Get locked tokens value for current block
    **/
    function getLockedTokens() public constant returns (uint256) {
        return getLockedTokens(block.number);
    }

    /**
    * @notice Terminate contract and refund to owner
    * @dev The called token contracts could try to re-enter this contract.
    Only supply token contracts you trust.
    **/
    function destroy() onlyBy(manager) public returns (bool) {
        if (token.transfer(owner, token.balanceOf(address(this)))) {
            // Transfer Eth to owner and terminate contract
            selfdestruct(owner);
            return true;
        } else {
            return true;
        }
    }

    /**
    * @notice Set mined decimals
    **/
    function setDecimals(uint256 _decimals) onlyBy(manager) {
        decimals = _decimals;
    }
}

/**
* Contract creates wallets and manage mining for that wallets
**/
contract WalletManager is Ownable {
    using LinkedList for LinkedList.Data;

    ERC20 token;
    mapping (address => Wallet) public wallets;
    LinkedList.Data walletOwners;
    uint256 miningCoefficient;
    uint256 lastMinedBlock;

    /**
    * @notice The WalletManager constructor sets address of token contract and mining coefficient
    * @param _token Token contract
    * @param _miningCoefficient amount of tokens that will be credited
    for each locked token in each iteration
    **/
    function WalletManager(ERC20 _token, uint256 _miningCoefficient) {
        token = _token;
        miningCoefficient = _miningCoefficient;
        lastMinedBlock = block.number;
    }

    /**
    * @notice Create wallet for user
    * @return Address of created wallet
    **/
    function createWallet() returns (address) {
        //TODO check existence
        Wallet wallet = new Wallet(token);
        wallet.transferOwnership(msg.sender);
        wallets[msg.sender] = wallet;
        if (!walletOwners.valueExists(msg.sender)) {
            walletOwners.push(msg.sender, true);
        }
        return wallet;
    }

    /**
    * @notice Lock some tokens
    * @param _value Amount of tokens which should lock
    * @param _releaseBlock Block number when tokens will be unlocked
    **/
    function lock(uint256 _value, uint256 _releaseBlock) returns (bool success) {
        return wallets[msg.sender].lock(_value, _releaseBlock);
    }

//    /**
//    * @notice Withdraw all amount of tokens back to owner (only if no locked)
//    **/
//    function withdrawAll()
//        whenNotLocked(msg.sender, tokenInfo[msg.sender].value)
//        returns (bool success)
//    {
//        if (!tokenOwners.valueExists(msg.sender)) {
//            return true;
//        }
//        tokenOwners.remove(msg.sender);
//        uint256 value = tokenInfo[msg.sender].value;
//        delete tokenInfo[msg.sender];
//        if (!token.transfer(msg.sender, value)) {
//            revert();
//            return false;
//        }
//        return true;
//    }

    /**
    * @notice Terminate contract and refund to owners
    * @dev The called token contracts could try to re-enter this contract.
    Only supply token contracts you trust.
    **/
    function destroy() onlyOwner public {
        // Transfer tokens to owners
        var current = walletOwners.step(0x0, true);
        while (current != 0x0) {
            //TODO handle errors
            wallets[current].destroy();
            current = walletOwners.step(current, true);
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
        return wallets[_owner].getLockedTokens(_blockNumber);
    }

    /**
    * @notice Get locked tokens value for all owners in a specified moment in time
    * @param _blockNumber Block number for checking
    **/
    function getAllLockedTokens(uint256 _blockNumber)
        public constant returns (uint256 result)
    {
        var current = walletOwners.step(0x0, true);
        while (current != 0x0) {
            result += getLockedTokens(current, _blockNumber);
            current = walletOwners.step(current, true);
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
    function mine() onlyOwner {
        var current = walletOwners.step(0x0, true);
        var minedBlocks = block.number - lastMinedBlock;
        while (current != 0x0) {
            Wallet wallet = wallets[current];
            var lockedValue = wallet.lockedValue();
            if (wallet.releaseBlock() > lastMinedBlock && lockedValue > 0) {
                var lockedBlocks = minedBlocks;
                var lockedBlock = wallet.lockedBlock();
                var releaseBlock = wallet.releaseBlock();
                if (lastMinedBlock < lockedBlock) {
                    lockedBlocks -= lockedBlock - lastMinedBlock;
                }
                if (block.number > releaseBlock) {
                    lockedBlocks -= block.number - releaseBlock;
                }
                //TODO handle overflow
                var minedValue = lockedBlocks * lockedValue + wallet.decimals();
                //TODO handle errors
                token.transfer(wallet, minedValue / miningCoefficient);
                wallet.setDecimals(minedValue % miningCoefficient);
            }
            current = walletOwners.step(current, true);
        }
        lastMinedBlock = block.number;
    }
}
