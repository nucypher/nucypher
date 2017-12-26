pragma solidity ^0.4.8;


import "./zeppelin/token/SafeERC20.sol";
import "./zeppelin/ownership/Ownable.sol";
import "./zeppelin/math/Math.sol";
import "./lib/LinkedList.sol";
import "./Miner.sol";
import "./NuCypherKMSToken.sol";


/**
* @notice Contract holds and locks client tokens.
Each client that lock his tokens will receive some compensation
**/
contract Escrow is Miner, Ownable {
    using LinkedList for LinkedList.Data;
    using SafeERC20 for NuCypherKMSToken;

    struct TokenInfo {
        uint256 value;
        uint256 lockedValue;
        uint256 lockedBlock;
        uint256 releaseBlock;
        uint256 decimals;
        uint256[] confirmedPeriods;
        uint256 numberConfirmedPeriods;
    }

    struct PeriodInfo {
        uint256 totalLockedValue;
        uint256 numberOwnersToBeRewarded;
    }

    uint256 constant MAX_PERIODS = 100;

    NuCypherKMSToken token;
    mapping (address => TokenInfo) public tokenInfo;
    LinkedList.Data tokenOwners;

    uint256 public blocksPerPeriod;
    mapping (uint256 => PeriodInfo) public lockedPerPeriod;

    /**
    * @notice The Escrow constructor sets address of token contract and coefficients for mining
    * @param _token Token contract
    * @param _miningCoefficient Mining coefficient
    * @param _blocksPerPeriod Size of one period in blocks
    **/
    function Escrow(
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
    * @notice Deposit tokens
    * @param _value Amount of token to deposit
    * @param _blocks Amount of blocks during which tokens will be locked
    **/
    function deposit(uint256 _value, uint256 _blocks) returns (bool success) {
        require(_value != 0);
        if (!tokenOwners.valueExists(msg.sender)) {
            tokenOwners.push(msg.sender, true);
        }
        tokenInfo[msg.sender].value = tokenInfo[msg.sender].value.add(_value);
        token.safeTransferFrom(msg.sender, address(this), _value);
        return lock(_value, _blocks);
    }

    /**
    * @notice Lock some tokens or increase lock
    * @param _value Amount of tokens which should lock
    * @param _blocks Amount of blocks during which tokens will be locked
    **/
    function lock(uint256 _value, uint256 _blocks) returns (bool success) {
        require(_value != 0 || _blocks != 0);
        var info = tokenInfo[msg.sender];
        uint256 lockedTokens = 0;
        if (!allTokensMinted()) {
            lockedTokens = info.lockedValue;
        }
        require(_value <= token.balanceOf(address(this)) &&
            _value <= info.value.sub(lockedTokens));
        // Checks if tokens are not locked or lock can be increased
        // TODO add checking amount of reward
        require(lockedTokens == 0 ||
            info.releaseBlock >= block.number);
        if (lockedTokens == 0) {
            info.lockedValue = _value;
            info.releaseBlock = block.number.add(_blocks);
            info.lockedBlock = block.number;
        } else {
            info.lockedValue = info.lockedValue.add(_value);
            info.releaseBlock = info.releaseBlock.add(_blocks);
        }
        confirmActivity();
        return true;
    }

    /**
    * @notice Withdraw available amount of tokens back to owner
    * @param _value Amount of token to withdraw
    **/
    function withdraw(uint256 _value) returns (bool success) {
        require(_value <= token.balanceOf(address(this)) &&
            _value <= tokenInfo[msg.sender].value - getLockedTokens(msg.sender));
        tokenInfo[msg.sender].value -= _value;
        token.safeTransfer(msg.sender, _value);
        return true;
    }

    /**
    * @notice Withdraw all amount of tokens back to owner (only if no locked)
    **/
    function withdrawAll() returns (bool success) {
        if (!tokenOwners.valueExists(msg.sender)) {
            return true;
        }
        uint256 value = tokenInfo[msg.sender].value;
        require(value <= token.balanceOf(address(this)) && allTokensMinted());
        tokenOwners.remove(msg.sender);
        delete tokenInfo[msg.sender];
        token.safeTransfer(msg.sender, value);
        return true;
    }

    /**
    * @notice Terminate contract and refund to owners
    * @dev The called token contracts could try to re-enter this contract.
    Only supply token contracts you trust.
    **/
    function destroy() onlyOwner public {
        // Transfer tokens to owners
        var current = tokenOwners.step(0x0, true);
        while (current != 0x0) {
            token.safeTransfer(current, tokenInfo[current].value);
            current = tokenOwners.step(current, true);
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
        if (tokenInfo[_owner].releaseBlock <= _blockNumber) {
            return 0;
        } else {
            return tokenInfo[_owner].lockedValue;
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
    * @notice Get locked tokens value for all owners in current period
    **/
    function getAllLockedTokens()
        public constant returns (uint256 result)
    {
        var currentPeriod = block.number / blocksPerPeriod;
        return lockedPerPeriod[currentPeriod].totalLockedValue;
    }

    /**
    * @notice Checks if sender has locked tokens which have not yet used in minting
    **/
    function allTokensMinted()
        internal constant returns (bool)
    {
        var info = tokenInfo[msg.sender];
        if (info.lockedValue == 0) {
            return true;
        }
        var releasePeriod = info.releaseBlock / blocksPerPeriod + 1;
        return block.number >= releasePeriod * blocksPerPeriod &&
            info.numberConfirmedPeriods == 0;
    }

    /**
    * @notice Confirm activity for future period
    **/
    function confirmActivity() {
        var info = tokenInfo[msg.sender];
        uint256 nextPeriod = block.number / blocksPerPeriod + 1;
        require(nextPeriod <= info.releaseBlock / blocksPerPeriod);

        if (info.numberConfirmedPeriods > 0 &&
            info.confirmedPeriods[info.numberConfirmedPeriods - 1] >= nextPeriod) {
           return;
        }
        require(info.numberConfirmedPeriods < MAX_PERIODS);
        lockedPerPeriod[nextPeriod].totalLockedValue += info.lockedValue;
        lockedPerPeriod[nextPeriod].numberOwnersToBeRewarded++;
        if (info.numberConfirmedPeriods < info.confirmedPeriods.length) {
            info.confirmedPeriods[info.numberConfirmedPeriods] = nextPeriod;
        } else {
            info.confirmedPeriods.push(nextPeriod);
        }
        info.numberConfirmedPeriods++;
    }

    /**
    * @notice Mint tokens for sender for previous periods if he locked his tokens and confirmed activity
    **/
    function mint() {
        require(!allTokensMinted());

        var previousPeriod = block.number / blocksPerPeriod - 1;
        var info = tokenInfo[msg.sender];
        var numberPeriodsForMinting = info.numberConfirmedPeriods;
        require(numberPeriodsForMinting > 0 &&
            info.confirmedPeriods[0] <= previousPeriod);

        var decimals = info.decimals;
        if (info.confirmedPeriods[numberPeriodsForMinting - 1] > previousPeriod) {
            numberPeriodsForMinting--;
        }
        if (info.confirmedPeriods[numberPeriodsForMinting - 1] > previousPeriod) {
            numberPeriodsForMinting--;
        }

        for(uint i = 0; i < numberPeriodsForMinting; ++i) {
            var period = info.confirmedPeriods[i];
            var periodFirstBlock = period * blocksPerPeriod;
            var periodLastBlock = (period + 1) * blocksPerPeriod - 1;
            var lockedBlocks = Math.min256(periodLastBlock, info.releaseBlock) -
                Math.max256(info.lockedBlock, periodFirstBlock);
            (, decimals) = mint(
                msg.sender,
                info.lockedValue,
                lockedPerPeriod[period].totalLockedValue,
                lockedBlocks,
                decimals);
            if (lockedPerPeriod[period].numberOwnersToBeRewarded > 1) {
                lockedPerPeriod[period].numberOwnersToBeRewarded--;
            } else {
                delete lockedPerPeriod[period];
            }
        }
        info.decimals = decimals;
        // Copy not minted periods
        var newNumberConfirmedPeriods = info.numberConfirmedPeriods - numberPeriodsForMinting;
        for (i = 0; i < newNumberConfirmedPeriods; i++) {
            info.confirmedPeriods[i] = info.confirmedPeriods[numberPeriodsForMinting + i];
        }
        info.numberConfirmedPeriods = newNumberConfirmedPeriods;
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
        var currentPeriod = block.number / blocksPerPeriod;
        uint256 distance = 0;
        uint256 lockedTokens = 0;
        var current = _start;

        if (current == 0x0)
            current = tokenOwners.step(current, true);

        while (current != 0x0) {
            var info = tokenInfo[current];
            var numberConfirmedPeriods = info.numberConfirmedPeriods;
            if (numberConfirmedPeriods == 0 ||
                info.confirmedPeriods[numberConfirmedPeriods - 1] != currentPeriod &&
                (numberConfirmedPeriods == 1 ||
                info.confirmedPeriods[numberConfirmedPeriods - 2] != currentPeriod)) {
                current = tokenOwners.step(current, true);
                continue;
            }
            lockedTokens = info.lockedValue;
            if (_delta < distance + lockedTokens) {
                o_stop = current;
                o_shift = _delta - distance;
                break;
            } else {
                distance += lockedTokens;
                current = tokenOwners.step(current, true);
            }
        }
    }
}
