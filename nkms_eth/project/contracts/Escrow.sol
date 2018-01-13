pragma solidity ^0.4.8;


import "./zeppelin/token/SafeERC20.sol";
import "./zeppelin/ownership/Ownable.sol";
import "./zeppelin/math/Math.sol";
import "./lib/AdditionalMath.sol";
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
    using AdditionalMath for uint256;

    struct ConfirmedPeriodInfo {
        uint256 period;
        uint256 lockedValue;
    }

    struct TokenInfo {
        uint256 value;
        uint256 decimals;
        uint256 lockedValue;
        bool release;
        uint256 maxReleasePeriods;
        uint256 releaseRate;
        ConfirmedPeriodInfo[] confirmedPeriods;
        uint256 numberConfirmedPeriods;
    }

    struct PeriodInfo {
        uint256 totalLockedValue;
        uint256 numberOwnersToBeRewarded;
    }

    uint256 constant MAX_PERIODS = 100;
    uint256 constant MAX_OWNERS = 50000;

    NuCypherKMSToken token;
    mapping (address => TokenInfo) public tokenInfo;
    LinkedList.Data tokenOwners;

    uint256 public blocksPerPeriod;
    mapping (uint256 => PeriodInfo) public lockedPerPeriod;
    uint256 public minReleasePeriods;

    /**
    * @notice The Escrow constructor sets address of token contract and coefficients for mining
    * @param _token Token contract
    * @param _miningCoefficient Mining coefficient
    * @param _blocksPerPeriod Size of one period in blocks
    * @param _minReleasePeriods Min amount of periods during which tokens will be released
    * @param _lockedBlocksCoefficient Locked blocks coefficient
    * @param _awardedPeriods Max periods that will be additionally awarded
    **/
    function Escrow(
        NuCypherKMSToken _token,
        uint256 _miningCoefficient,
        uint256 _blocksPerPeriod,
        uint256 _minReleasePeriods,
        uint256 _lockedBlocksCoefficient,
        uint256 _awardedPeriods
    )
        Miner(_token, _miningCoefficient, _lockedBlocksCoefficient, _awardedPeriods * _blocksPerPeriod)
    {
        require(_blocksPerPeriod != 0 && _minReleasePeriods != 0);
        token = _token;
        blocksPerPeriod = _blocksPerPeriod;
        minReleasePeriods = _minReleasePeriods;
    }

    /**
    * @notice Get locked tokens value for owner in current period
    * @param _owner Tokens owner
    **/
    function getLockedTokens(address _owner)
        public constant returns (uint256)
    {
        var currentPeriod = block.number.div(blocksPerPeriod);
        var info = tokenInfo[_owner];
        var numberConfirmedPeriods = info.numberConfirmedPeriods;

        // no confirmed periods, so current period may be release period
        if (numberConfirmedPeriods == 0) {
            var lockedValue = info.lockedValue;
        } else {
            var i = numberConfirmedPeriods - 1;
            var confirmedPeriod = info.confirmedPeriods[i].period;
            // last confirmed period is current period
            if (confirmedPeriod == currentPeriod) {
                return info.confirmedPeriods[i].lockedValue;
            // last confirmed period is previous periods, so current period may be release period
            } else if (confirmedPeriod < currentPeriod) {
                lockedValue = info.confirmedPeriods[i].lockedValue;
            // penultimate confirmed period is previous or current period, so get its lockedValue
            } else if (numberConfirmedPeriods > 1) {
                return info.confirmedPeriods[numberConfirmedPeriods - 2].lockedValue;
            // no previous periods, so return saved lockedValue
            } else {
                return info.lockedValue;
            }
        }
        // checks if owner can mine more tokens (before or after release period)
        if (calculateLockedTokens(_owner, false, lockedValue, 1) == 0) {
            return 0;
        } else {
            return lockedValue;
        }
    }

    /**
    * @notice Get locked tokens value for all owners in current period
    **/
    function getAllLockedTokens()
        public constant returns (uint256)
    {
        var period = block.number.div(blocksPerPeriod);
        return lockedPerPeriod[period].totalLockedValue;
    }

    /**
    * @notice Calculate locked tokens value for owner in next period
    * @param _owner Tokens owner
    * @param _forceRelease Force unlocking period calculation
    * @param _lockedTokens Locked tokens in specified period
    * @param _periods Number of periods that need to calculate
    * @return Calculated locked tokens in next period
    **/
    function calculateLockedTokens(
        address _owner,
        bool _forceRelease,
        uint256 _lockedTokens,
        uint256 _periods
    )
        internal constant returns (uint256)
    {
        var info = tokenInfo[_owner];
        if ((_forceRelease || info.release) && _periods != 0) {
            var unlockedTokens = _periods.mul(info.releaseRate);
            return unlockedTokens <= _lockedTokens ? _lockedTokens.sub(unlockedTokens) : 0;
        } else {
            return _lockedTokens;
        }
    }

    /**
    * @notice Calculate locked tokens value for owner in next period
    * @param _owner Tokens owner
    * @param _periods Number of periods after current that need to calculate
    * @return Calculated locked tokens in next period
    **/
    function calculateLockedTokens(address _owner, uint256 _periods)
        public constant returns (uint256)
    {
        require(_periods > 0);
        var currentPeriod = block.number.div(blocksPerPeriod);
        var nextPeriod = currentPeriod.add(_periods);

        var info = tokenInfo[_owner];
        var numberConfirmedPeriods = info.numberConfirmedPeriods;
        if (numberConfirmedPeriods > 0 &&
            info.confirmedPeriods[numberConfirmedPeriods - 1].period >= currentPeriod) {
            var lockedTokens = info.confirmedPeriods[numberConfirmedPeriods - 1].lockedValue;
            var period = info.confirmedPeriods[numberConfirmedPeriods - 1].period;
        } else {
            lockedTokens = getLockedTokens(_owner);
            period = currentPeriod;
        }
        var periods = nextPeriod.sub(period);

        return calculateLockedTokens(_owner, false, lockedTokens, periods);
    }

    /**
    * @notice Calculate locked periods for owner from start period
    * @param _owner Tokens owner
    * @param _lockedTokens Locked tokens in start period
    * @return Calculated locked periods
    **/
    function calculateLockedPeriods(
        address _owner,
        uint256 _lockedTokens
    )
        internal constant returns (uint256)
    {
        var info = tokenInfo[_owner];
        return _lockedTokens.divCeil(info.releaseRate).sub(1);
    }

    /**
    * @notice Deposit tokens
    * @param _value Amount of token to deposit
    * @param _periods Amount of periods during which tokens will be unlocked
    **/
    function deposit(uint256 _value, uint256 _periods) public {
        require(_value != 0);
        if (!tokenOwners.valueExists(msg.sender)) {
            require(tokenOwners.sizeOf() < MAX_OWNERS);
            tokenOwners.push(msg.sender, true);
        }
        var info = tokenInfo[msg.sender];
        info.value = info.value.add(_value);
        token.safeTransferFrom(msg.sender, address(this), _value);
        lock(_value, _periods);
    }

    /**
    * @notice Lock some tokens or increase lock
    * @param _value Amount of tokens which should lock
    * @param _periods Amount of periods during which tokens will be unlocked
    **/
    function lock(uint256 _value, uint256 _periods) public {
        // TODO add checking min _value
        require(_value != 0 || _periods != 0);

        var lockedTokens = calculateLockedTokens(msg.sender, 1);
        var info = tokenInfo[msg.sender];
        require(_value <= token.balanceOf(address(this)) &&
            _value <= info.value.sub(lockedTokens));

        var currentPeriod = block.number.div(blocksPerPeriod);
        if (lockedTokens == 0) {
            info.lockedValue = _value;
            info.maxReleasePeriods = Math.max256(_periods, minReleasePeriods);
            info.releaseRate = Math.max256(_value.divCeil(info.maxReleasePeriods), 1);
            info.release = false;
        } else {
            info.lockedValue = lockedTokens.add(_value);
            info.maxReleasePeriods = info.maxReleasePeriods.add(_periods);
            info.releaseRate = Math.max256(
                info.lockedValue.divCeil(info.maxReleasePeriods), info.releaseRate);
        }

        confirmActivity(info.lockedValue);
    }

    /**
    * @notice Switch lock
    **/
    function switchLock() public {
        var info = tokenInfo[msg.sender];
        info.release = !info.release;
    }

    /**
    * @notice Withdraw available amount of tokens back to owner
    * @param _value Amount of token to withdraw
    **/
    function withdraw(uint256 _value) public {
        var info = tokenInfo[msg.sender];
        // TODO optimize
        var lockedTokens = Math.max256(calculateLockedTokens(msg.sender, 1),
            getLockedTokens(msg.sender));
        require(_value <= token.balanceOf(address(this)) &&
            _value <= info.value.sub(lockedTokens));
        info.value -= _value;
        token.safeTransfer(msg.sender, _value);
    }

    /**
    * @notice Withdraw all amount of tokens back to owner (only if no locked)
    **/
    function withdrawAll() public {
        // TODO extract modifier
        require(tokenOwners.valueExists(msg.sender));
        var info = tokenInfo[msg.sender];
        var value = info.value;
        require(value <= token.balanceOf(address(this)) &&
            info.lockedValue == 0 &&
            info.numberConfirmedPeriods == 0);
        tokenOwners.remove(msg.sender);
        delete tokenInfo[msg.sender];
        token.safeTransfer(msg.sender, value);
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
    * @notice Confirm activity for future period
    * @param _lockedValue Locked tokens in future period
    **/
    function confirmActivity(uint256 _lockedValue) internal {
        require(_lockedValue > 0);
        var info = tokenInfo[msg.sender];
        var nextPeriod = block.number.div(blocksPerPeriod) + 1;

        var numberConfirmedPeriods = info.numberConfirmedPeriods;
        if (numberConfirmedPeriods > 0 &&
            info.confirmedPeriods[numberConfirmedPeriods - 1].period == nextPeriod) {
            var confirmedPeriod = info.confirmedPeriods[numberConfirmedPeriods - 1];
            lockedPerPeriod[nextPeriod].totalLockedValue = lockedPerPeriod[nextPeriod].totalLockedValue
                .add(_lockedValue.sub(confirmedPeriod.lockedValue));
            confirmedPeriod.lockedValue = _lockedValue;
            return;
        }

        require(numberConfirmedPeriods < MAX_PERIODS);
        lockedPerPeriod[nextPeriod].totalLockedValue =
            lockedPerPeriod[nextPeriod].totalLockedValue.add(_lockedValue);
        lockedPerPeriod[nextPeriod].numberOwnersToBeRewarded++;
        if (numberConfirmedPeriods < info.confirmedPeriods.length) {
            info.confirmedPeriods[numberConfirmedPeriods].period = nextPeriod;
            info.confirmedPeriods[numberConfirmedPeriods].lockedValue = _lockedValue;
        } else {
            info.confirmedPeriods.push(ConfirmedPeriodInfo(nextPeriod, _lockedValue));
        }
        info.numberConfirmedPeriods++;
    }

    /**
    * @notice Confirm activity for future period
    **/
    function confirmActivity() external {
        var info = tokenInfo[msg.sender];
        var nextPeriod = block.number.div(blocksPerPeriod) + 1;

        if (info.numberConfirmedPeriods > 0 &&
            info.confirmedPeriods[info.numberConfirmedPeriods - 1].period >= nextPeriod) {
           return;
        }

        var currentPeriod = nextPeriod - 1;
        var lockedTokens = calculateLockedTokens(
            msg.sender, false, getLockedTokens(msg.sender), 1);
        confirmActivity(lockedTokens);
    }

    /**
    * @notice Mint tokens for sender for previous periods if he locked his tokens and confirmed activity
    **/
    function mint() external {
        var previousPeriod = block.number.div(blocksPerPeriod).sub(1);
        var info = tokenInfo[msg.sender];
        var numberPeriodsForMinting = info.numberConfirmedPeriods;
        require(numberPeriodsForMinting > 0 &&
            info.confirmedPeriods[0].period <= previousPeriod);

        var currentLockedValue = getLockedTokens(msg.sender);
        var allLockedBlocks = calculateLockedPeriods(
            msg.sender,
            info.confirmedPeriods[numberPeriodsForMinting - 1].lockedValue)
            .add(numberPeriodsForMinting)
            .mul(blocksPerPeriod);
        var decimals = info.decimals;

        if (info.confirmedPeriods[numberPeriodsForMinting - 1].period > previousPeriod) {
            numberPeriodsForMinting--;
        }
        if (info.confirmedPeriods[numberPeriodsForMinting - 1].period > previousPeriod) {
            numberPeriodsForMinting--;
        }

        for(uint i = 0; i < numberPeriodsForMinting; ++i) {
            var period = info.confirmedPeriods[i].period;
            var lockedValue = info.confirmedPeriods[i].lockedValue;
            allLockedBlocks = allLockedBlocks.sub(blocksPerPeriod);
            (, decimals) = mint(
                msg.sender,
                lockedValue,
                lockedPerPeriod[period].totalLockedValue,
                blocksPerPeriod,
                allLockedBlocks,
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

        // Update lockedValue for current period
        info.lockedValue = currentLockedValue;
    }

    /**
    * @notice Fixed-step in cumulative sum
    * @param _start Starting point
    * @param _delta How much to step
    * @param _periods Amount of periods to get locked tokens
    * @dev
             _start
                v
      |-------->*--------------->*---->*------------->|
                |                      ^
                |                      stop
                |
                |       _delta
                |---------------------------->|
                |
                |                       shift
                |                      |----->|
    **/
    function findCumSum(address _start, uint256 _delta, uint256 _periods)
        public constant returns (address stop, uint256 shift)
    {
        require(_periods > 0);
        var currentPeriod = block.number.div(blocksPerPeriod);
        uint256 distance = 0;
        var current = _start;

        if (current == 0x0) {
            current = tokenOwners.step(current, true);
        }

        while (current != 0x0) {
            var info = tokenInfo[current];
            var numberConfirmedPeriods = info.numberConfirmedPeriods;
            var period = currentPeriod;
            if (numberConfirmedPeriods > 0 &&
                info.confirmedPeriods[numberConfirmedPeriods - 1].period == currentPeriod) {
                var lockedTokens = calculateLockedTokens(
                    current,
                    true,
                    info.confirmedPeriods[numberConfirmedPeriods - 1].lockedValue,
                    _periods);
            } else if (numberConfirmedPeriods > 1 &&
                info.confirmedPeriods[numberConfirmedPeriods - 2].period == currentPeriod) {
                lockedTokens = calculateLockedTokens(
                    current,
                    true,
                    info.confirmedPeriods[numberConfirmedPeriods - 1].lockedValue,
                    _periods - 1);
            } else {
                current = tokenOwners.step(current, true);
                continue;
            }

            if (_delta < distance + lockedTokens) {
                stop = current;
                shift = _delta - distance;
                break;
            } else {
                distance += lockedTokens;
                current = tokenOwners.step(current, true);
            }
        }
    }
}
