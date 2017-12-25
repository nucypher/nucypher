pragma solidity ^0.4.8;


import "./zeppelin/token/SafeERC20.sol";
import "./zeppelin/math/SafeMath.sol";
import "./zeppelin/math/Math.sol";
import "./zeppelin/ownership/Ownable.sol";
import "./NuCypherKMSToken.sol";
import "./lib/LinkedList.sol";
import "./Miner.sol";
import "./Wallet.sol";


/**
* @notice Contract creates wallets and manage mining for that wallets
**/
contract WalletManager is Miner, Ownable {
    using LinkedList for LinkedList.Data;
    using SafeERC20 for NuCypherKMSToken;

    struct PeriodInfo {
        uint256 totalLockedValue;
        uint256 numberOwnersToBeRewarded;
    }

    uint256 constant MAX_PERIODS = 100;

    NuCypherKMSToken token;
    mapping (address => Wallet) public wallets;
    LinkedList.Data walletOwners;

    uint256 public blocksPerPeriod;
    mapping (uint256 => PeriodInfo) public lockedPerPeriod;

    /**
    * @notice The WalletManager constructor sets address of token contract and coefficients for mining
    * @param _token Token contract
    * @param _miningCoefficient Mining coefficient
    **/
    function WalletManager(
        NuCypherKMSToken _token,
        uint256 _miningCoefficient,
        uint256 _blocksPerPeriod
    )
        Miner(_token, _miningCoefficient)
    {
        require(_blocksPerPeriod != 0);
        token = _token;
        blocksPerPeriod = _blocksPerPeriod;
    }

    /**
    * @dev Throws if called by account that have not wallet.
    */
    modifier walletExists() {
        require(walletOwners.valueExists(msg.sender));
        _;
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
    function lock(uint256 _value, uint256 _blocks)
        walletExists
        returns (bool success)
    {
        require(_value != 0 || _blocks != 0);
        Wallet wallet = wallets[msg.sender];

        uint256 lockedTokens = 0;
        if (!allTokensMinted()) {
            lockedTokens = wallet.lockedValue();
        }
        require(_value <= token.balanceOf(wallet).sub(lockedTokens));
        // Checks if tokens are not locked or lock can be increased
        // TODO add checking reward
        require(lockedTokens == 0 ||
            wallet.releaseBlock() >= block.number);
        if (lockedTokens == 0) {
            wallet.setLock(_value, block.number.add(_blocks), block.number);
        } else {
            wallet.setLock(
                wallet.lockedValue().add(_value),
                wallet.releaseBlock().add(_blocks),
                wallet.lockedBlock()
            );
        }
        confirmActivity();
        return true;
    }

    // FIXME bug with big file size. Can't deploy contract even with maximum gas if uncomment
//    /**
//    * @notice Terminate contract and refund to owners
//    * @dev The called token contracts could try to re-enter this contract.
//    Only supply token contracts you trust.
//    **/
//    function destroy() onlyOwner public {
//        // Transfer tokens to owners
//        var current = walletOwners.step(0x0, true);
//        while (current != 0x0) {
//            wallets[current].destroy();
//            current = walletOwners.step(current, true);
//        }
//        token.safeTransfer(owner, token.balanceOf(address(this)));
//
//        // Transfer Eth to owner and terminate contract
//        selfdestruct(owner);
//    }

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

    /**
    * @notice Checks if sender has locked tokens which have not yet used in minting
    **/
    function allTokensMinted()
        internal constant returns (bool)
    {
        var wallet = wallets[msg.sender];
        if (wallet.lockedValue() == 0) {
            return true;
        }
        var releasePeriod = wallet.releaseBlock() / blocksPerPeriod + 1;
        uint256 numberConfirmedPeriods = wallet.numberConfirmedPeriods();
        return block.number >= releasePeriod * blocksPerPeriod &&
            numberConfirmedPeriods == 0;
//            (numberConfirmedPeriods == 0 ||
//	        wallet.confirmedPeriods(numberConfirmedPeriods - 1) > releasePeriod);
    }

    /**
    * @notice Confirm activity for future period
    **/
    function confirmActivity() walletExists {
        var wallet = wallets[msg.sender];
        uint256 nextPeriod = block.number / blocksPerPeriod + 1;
        require(nextPeriod <= wallet.releaseBlock() / blocksPerPeriod);

        uint256 numberConfirmedPeriods = wallet.numberConfirmedPeriods();
        if (numberConfirmedPeriods > 0 &&
            wallet.confirmedPeriods(numberConfirmedPeriods - 1) >= nextPeriod) {
           return;
        }
        require(numberConfirmedPeriods < MAX_PERIODS);
        lockedPerPeriod[nextPeriod].totalLockedValue += wallet.lockedValue();
        lockedPerPeriod[nextPeriod].numberOwnersToBeRewarded++;
        wallet.addConfirmedPeriod(nextPeriod);
    }

    /**
    * @notice Mint tokens for sender for previous periods if he locked his tokens and confirmed activity
    **/
    function mint() walletExists {
        require(!allTokensMinted());

        var previousPeriod = block.number / blocksPerPeriod - 1;
        Wallet wallet = wallets[msg.sender];
        var numberPeriodsForMinting = wallet.numberConfirmedPeriods();
        require(numberPeriodsForMinting > 0 &&
            wallet.confirmedPeriods(0) <= previousPeriod);

        var decimals = wallet.decimals();
        if (wallet.confirmedPeriods(numberPeriodsForMinting - 1) > previousPeriod) {
            numberPeriodsForMinting--;
        }
        if (wallet.confirmedPeriods(numberPeriodsForMinting - 1) > previousPeriod) {
            numberPeriodsForMinting--;
        }

        for(uint i = 0; i < numberPeriodsForMinting; ++i) {
            var period = wallet.confirmedPeriods(i);
            var periodFirstBlock = period * blocksPerPeriod;
            var periodLastBlock = (period + 1) * blocksPerPeriod - 1;
            var lockedBlocks = Math.min256(periodLastBlock, wallet.releaseBlock()) -
                Math.max256(wallet.lockedBlock(), periodFirstBlock);
            (, decimals) = mint(
                wallet,
                wallet.lockedValue(),
                lockedPerPeriod[period].totalLockedValue,
                lockedBlocks,
                decimals);
            if (lockedPerPeriod[period].numberOwnersToBeRewarded > 1) {
                lockedPerPeriod[period].numberOwnersToBeRewarded--;
            } else {
                delete lockedPerPeriod[period];
            }
        }
        wallet.setDecimals(decimals);
        wallet.deleteConfirmedPeriod(numberPeriodsForMinting);
    }

    /**
    * @notice Fixedstep in cumsum
    * @param _start Starting point
    * @param _delta How much to step
    * @dev
      |-------->*--------------->*---->*------------->|
                |                      ^
                |                      o_stop
                |
                |       _delta
                |---------------------------->|
                |
                |                       o_shift
                |                      |----->|
    **/
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
}
