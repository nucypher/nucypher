pragma solidity ^0.4.8;


import "zeppelin-solidity/contracts/token/ERC20.sol";
import "zeppelin-solidity/contracts/token/SafeERC20.sol";
import "zeppelin-solidity/contracts/math/SafeMath.sol";
import "zeppelin-solidity/contracts/math/Math.sol";
import "zeppelin-solidity/contracts/ownership/Ownable.sol";
import "./HumanStandardToken.sol";
import "./LinkedList.sol";
import "./Miner.sol";


/**
* @notice Contract holds and locks client tokens.
**/
contract Wallet is Ownable {
    using SafeERC20 for BurnableToken;
    using SafeMath for uint256;

    BurnableToken token;
    uint256 public lockedValue;
    uint256 public releaseBlock;
    uint256 public decimals;
    uint256 public lastMintedBlock;
    address manager;

    /**
    * @dev Throws if called by any account other than the manager.
    **/
    modifier onlyManager() {
        require(msg.sender == manager);
        _;
    }

    /**
    * @notice Wallet constructor set token contract
    * @param _token Token contract
    **/
    function Wallet(BurnableToken _token) {
        token = _token;
        manager = msg.sender;
    }

    /**
    * @notice Lock some tokens
    * @param _value Amount of tokens which should lock
    * @param _blocks Amount of blocks during which tokens will be locked
    **/
    function lock(uint256 _value, uint256 _blocks)
        onlyManager
//        onlyOwner
        returns (bool success)
    {
        require(_value != 0 || _blocks != 0);
        uint256 lastLockedTokens = getLastLockedTokens();
        require(_value <= token.balanceOf(address(this)).sub(lastLockedTokens));
        if (lastLockedTokens == 0) {
            lockedValue = _value;
            releaseBlock = block.number.add(_blocks);
            lastMintedBlock = block.number;
        } else {
            lockedValue = lockedValue.add(_value);
            releaseBlock = releaseBlock.add(_blocks);
        }
        return true;
    }

    /**
    * @notice Withdraw available amount of tokens back to owner
    * @param _value Amount of token to withdraw
    **/
    function withdraw(uint256 _value) onlyOwner returns (bool success) {
        require(_value <= token.balanceOf(address(this)) - getLockedTokens());
        token.safeTransfer(msg.sender, _value);
        return true;
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
    * @notice Get locked tokens value at the time of the last minted block
    **/
    function getLastLockedTokens() public constant returns (uint256) {
        return getLockedTokens(lastMintedBlock);
    }

    /**
    * @notice Terminate contract and refund to owner
    * @dev The called token contracts could try to re-enter this contract.
    Only supply token contracts you trust.
    **/
    function destroy() onlyManager public returns (bool) {
        token.safeTransfer(owner, token.balanceOf(address(this)));
        selfdestruct(owner);
        return true;
    }

    /**
    * @notice Set minted decimals
    **/
    function setDecimals(uint256 _decimals) onlyManager {
        decimals = _decimals;
    }

    /**
    * @notice Set last minted block
    **/
    function setLastMintedBlock(uint256 _lastMintedBlock) onlyManager {
        lastMintedBlock = _lastMintedBlock;
    }

    /**
    * @notice Burn locked tokens
    * @param _value Amount of tokens that will be confiscated
    **/
    function burn(uint256 _value) onlyManager {
        require(getLockedTokens() >= _value);
        lockedValue = lockedValue.sub(_value);
        token.burn(_value);
    }
}

/**
* @notice Contract creates wallets and manage mining for that wallets
**/
contract WalletManager is Miner, Ownable {
    using LinkedList for LinkedList.Data;
    using SafeERC20 for HumanStandardToken;

    HumanStandardToken token;
    mapping (address => Wallet) public wallets;
    LinkedList.Data walletOwners;

    /**
    * @notice The WalletManager constructor sets address of token contract and coefficients for mining
    * @param _token Token contract
    * @param _rate Curve growing rate
    * @param _fractions Coefficient for fractions
    **/
    function WalletManager(HumanStandardToken _token, uint256 _rate, uint256 _fractions)
        Miner(_token, _rate, _fractions)
    {
        token = _token;
    }

    /**
    * @notice Create wallet for user
    * @return Address of created wallet
    **/
    function createWallet() returns (address) {
        require(!walletOwners.valueExists(msg.sender));
        Wallet wallet = new Wallet(token);
        wallet.transferOwnership(msg.sender);
        wallets[msg.sender] = wallet;
        walletOwners.push(msg.sender, true);
        return wallet;
    }

    /**
    * @notice Lock some tokens
    * @param _value Amount of tokens which should lock
    * @param _blocks Amount of blocks during which tokens will be locked
    **/
    function lock(uint256 _value, uint256 _blocks) returns (bool success) {
        require(walletOwners.valueExists(msg.sender));
        Wallet wallet = wallets[msg.sender];
        uint256 lastLockedTokens = wallet.getLastLockedTokens();
        // Checks if tokens are not locked or lock can be increased
        require(
            lastLockedTokens == 0 &&
            !isEmptyReward(_value, _blocks) ||
            lastLockedTokens != 0 &&
            wallet.releaseBlock() >= block.number &&
            !isEmptyReward(_value + wallet.lockedValue(),
                _blocks + wallet.releaseBlock() - wallet.lastMintedBlock())
        );
        return wallet.lock(_value, _blocks);
    }

    /**
    * @notice Terminate contract and refund to owners
    * @dev The called token contracts could try to re-enter this contract.
    Only supply token contracts you trust.
    **/
    function destroy() onlyOwner public {
        // Transfer tokens to owners
        var current = walletOwners.step(0x0, true);
        while (current != 0x0) {
            wallets[current].destroy();
            current = walletOwners.step(current, true);
        }
        token.safeTransfer(owner, token.balanceOf(address(this)));

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

    /*
       Fixedstep in cumsum
       @start   Starting point
       @delta   How much to step

      |-------->*--------------->*---->*------------->|
                |                      ^
                |                      o_stop
                |
                |       _delta
                |---------------------------->|
                |
                |                       o_shift
                |                      |----->|
       */
      // _blockNumber?
    function findCumSum(address _start, uint256 _delta)
        public constant returns (address o_stop, uint256 o_shift)
    {
        require(walletOwners.valueExists(_start));
        uint256 distance = 0;
        uint256 lockedTokens = 0;
        var current = _start;

        if (current == 0x0)
            current = walletOwners.step(current, true);

        while (true) {
            lockedTokens = getLockedTokens(current);
            if (_delta < distance + lockedTokens) {
                o_stop = current;
                o_shift = _delta - distance;
                break;
            } else {
                distance += lockedTokens;
                current = walletOwners.step(current, true);
            }
        }
    }

    /**
    * @notice Mint tokens for sender if he locked his tokens
    **/
    function mint() {
        require(walletOwners.valueExists(msg.sender));
        Wallet wallet = wallets[msg.sender];
        require(wallet.getLastLockedTokens() != 0);
        var lockedBlocks = Math.min256(block.number, wallet.releaseBlock()) -
            wallet.lastMintedBlock();
        var (amount, decimals) =
            mint(wallet, wallet.lockedValue(), lockedBlocks, wallet.decimals());
        if (amount != 0) {
            wallet.setDecimals(decimals);
            wallet.setLastMintedBlock(block.number);
        }
    }

    /**
    * @notice Penalize token owner
    * @param _user Token owner
    * @param _value Amount of tokens that will be confiscated
    **/
    function penalize(address _user, uint256 _value)
        onlyOwner
        public returns (bool success)
    {
        require(walletOwners.valueExists(_user));
//        require(getLockedTokens(_user) >= _value);
        wallets[_user].burn(_value);
        return true;
    }
}
