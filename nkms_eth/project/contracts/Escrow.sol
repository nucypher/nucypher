pragma solidity ^0.4.8;


import "./zeppelin/token/SafeERC20.sol";
import "./zeppelin/ownership/Ownable.sol";
import "./zeppelin/math/Math.sol";
import "./lib/AdditionalMath.sol";
import "./lib/LinkedList.sol";
import "./Miner.sol";
import "./NuCypherKMSToken.sol";
import "./PolicyManager.sol";


/**
* @notice Contract holds and locks nodes tokens.
Each node that lock his tokens will receive some compensation
**/
contract Escrow is Miner, Ownable {
    using LinkedList for LinkedList.Data;
    using SafeERC20 for NuCypherKMSToken;
    using AdditionalMath for uint256;

    struct ConfirmedPeriodInfo {
        uint256 period;
        uint256 lockedValue;
    }

    struct Downtime {
        uint256 startPeriod;
        uint256 endPeriod;
    }

    struct TokenInfo {
        uint256 value;
        uint256 decimals;
        uint256 lockedValue;
        bool release;
        uint256 maxReleasePeriods;
        uint256 releaseRate;
        // periods that confirmed but not yet mined
        ConfirmedPeriodInfo[] confirmedPeriods;
        uint256 numberConfirmedPeriods;
        // downtime
        uint256 lastActivePeriod;
        Downtime[] downtime;
    }

    uint256 constant MAX_PERIODS = 10;
    uint256 constant MAX_OWNERS = 50000;

    mapping (address => TokenInfo) public tokenInfo;
    LinkedList.Data tokenOwners;

    mapping (uint256 => uint256) public lockedPerPeriod;
    uint256 public minReleasePeriods;
    uint256 public minAllowableLockedTokens;
    PolicyManager policyManager;

    /**
    * @notice The Escrow constructor sets address of token contract and coefficients for mining
    * @param _token Token contract
    * @param _hoursPerPeriod Size of period in hours
    * @param _miningCoefficient Mining coefficient
    * @param _minReleasePeriods Min amount of periods during which tokens will be released
    * @param _lockedPeriodsCoefficient Locked blocks coefficient
    * @param _awardedPeriods Max periods that will be additionally awarded
    * @param _minAllowableLockedTokens Min amount of tokens that can be locked
    **/
    function Escrow(
        NuCypherKMSToken _token,
        uint256 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint256 _awardedPeriods,
        uint256 _minReleasePeriods,
        uint256 _minAllowableLockedTokens
    )
        Miner(
            _token,
            _hoursPerPeriod,
            _miningCoefficient,
            _lockedPeriodsCoefficient,
            _awardedPeriods
        )
    {
        require(_minReleasePeriods != 0);
        minReleasePeriods = _minReleasePeriods;
        minAllowableLockedTokens = _minAllowableLockedTokens;
    }

    /**
    * @dev Checks that sender exists in contract
    **/
    modifier onlyTokenOwner()
    {
        require(tokenOwners.valueExists(msg.sender));
        _;
    }

    /**
    * @notice Get tokens value for owner
    * @param _owner Tokens owner
    **/
    function getTokens(address _owner)
        public constant returns (uint256)
    {
        return tokenInfo[_owner].value;
    }

    /**
    * @notice Get locked tokens value for owner in current period
    * @param _owner Tokens owner
    **/
    function getLockedTokens(address _owner)
        public constant returns (uint256)
    {
        var currentPeriod = getCurrentPeriod();
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
        return lockedPerPeriod[getCurrentPeriod()];
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
        var currentPeriod = getCurrentPeriod();
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
    * @notice Pre-deposit tokens
    * @param _owners Tokens owners
    * @param _values Amount of token to deposit for owners
    * @param _periods Amount of periods during which tokens will be unlocked
    **/
    function preDeposit(address[] _owners, uint256[] _values, uint256 _periods)
        public isInitialized onlyOwner
    {
        require(_owners.length != 0 &&
            tokenOwners.sizeOf().add(_owners.length) <= MAX_OWNERS &&
            _owners.length == _values.length &&
            _periods >= minReleasePeriods);
        var currentPeriod = getCurrentPeriod();
        uint256 allValue = 0;

        for (uint256 i = 0; i < _owners.length; i++) {
            var owner = _owners[i];
            var value = _values[i];
            require(!tokenOwners.valueExists(owner) &&
                value >= minAllowableLockedTokens);
            // TODO optimize
            tokenOwners.push(owner, true);
            var info = tokenInfo[owner];
            info.lastActivePeriod = currentPeriod;
            info.value = value;
            info.lockedValue = value;
            info.maxReleasePeriods = _periods;
            info.releaseRate = Math.max256(value.divCeil(_periods), 1);
            info.release = false;
            allValue = allValue.add(value);
        }

        token.safeTransferFrom(msg.sender, address(this), allValue);
    }

    /**
    * @notice Deposit tokens
    * @param _value Amount of token to deposit
    * @param _periods Amount of periods during which tokens will be unlocked
    **/
    function deposit(uint256 _value, uint256 _periods) public isInitialized {
        require(_value != 0);
        var info = tokenInfo[msg.sender];
        if (!tokenOwners.valueExists(msg.sender)) {
            require(tokenOwners.sizeOf() < MAX_OWNERS);
            tokenOwners.push(msg.sender, true);
            info.lastActivePeriod = getCurrentPeriod();
        }
        info.value = info.value.add(_value);
        token.safeTransferFrom(msg.sender, address(this), _value);
        lock(_value, _periods);
    }

    /**
    * @notice Lock some tokens or increase lock
    * @param _value Amount of tokens which should lock
    * @param _periods Amount of periods during which tokens will be unlocked
    **/
    function lock(uint256 _value, uint256 _periods) public onlyTokenOwner {
        require(_value != 0 || _periods != 0);

        var lockedTokens = calculateLockedTokens(msg.sender, 1);
        var info = tokenInfo[msg.sender];
        require(_value <= token.balanceOf(address(this)) &&
            _value <= info.value.sub(lockedTokens));

        var currentPeriod = getCurrentPeriod();
        if (lockedTokens == 0) {
            require(_value >= minAllowableLockedTokens);
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
    function switchLock() public onlyTokenOwner {
        var info = tokenInfo[msg.sender];
        info.release = !info.release;
    }

    /**
    * @notice Withdraw available amount of tokens back to owner
    * @param _value Amount of token to withdraw
    **/
    function withdraw(uint256 _value) public onlyTokenOwner {
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
    function withdrawAll() public onlyTokenOwner {
        var info = tokenInfo[msg.sender];
        var value = info.value;
        require(value <= token.balanceOf(address(this)) &&
            info.lockedValue == 0 &&
            info.numberConfirmedPeriods == 0);
        tokenOwners.remove(msg.sender);
        delete tokenInfo[msg.sender];
        token.safeTransfer(msg.sender, value);
    }

    // TODO change to upgrade
//    /**
//    * @notice Terminate contract and refund to owners
//    * @dev The called token contracts could try to re-enter this contract.
//    Only supply token contracts you trust.
//    **/
//    function destroy() onlyOwner public {
//        // Transfer tokens to owners
//        var current = tokenOwners.step(0x0, true);
//        while (current != 0x0) {
//            token.safeTransfer(current, tokenInfo[current].value);
//            current = tokenOwners.step(current, true);
//        }
//        token.safeTransfer(owner, token.balanceOf(address(this)));
//
//        // Transfer Eth to owner and terminate contract
//        selfdestruct(owner);
//    }

    /**
    * @notice Confirm activity for future period
    * @param _lockedValue Locked tokens in future period
    **/
    function confirmActivity(uint256 _lockedValue) internal {
        require(_lockedValue > 0);
        var info = tokenInfo[msg.sender];
        var nextPeriod = getCurrentPeriod() + 1;

        var numberConfirmedPeriods = info.numberConfirmedPeriods;
        if (numberConfirmedPeriods > 0 &&
            info.confirmedPeriods[numberConfirmedPeriods - 1].period == nextPeriod) {
            var confirmedPeriod = info.confirmedPeriods[numberConfirmedPeriods - 1];
            lockedPerPeriod[nextPeriod] = lockedPerPeriod[nextPeriod]
                .add(_lockedValue.sub(confirmedPeriod.lockedValue));
            confirmedPeriod.lockedValue = _lockedValue;
            return;
        }

        require(numberConfirmedPeriods < MAX_PERIODS);
        lockedPerPeriod[nextPeriod] = lockedPerPeriod[nextPeriod]
            .add(_lockedValue);
        if (numberConfirmedPeriods < info.confirmedPeriods.length) {
            info.confirmedPeriods[numberConfirmedPeriods].period = nextPeriod;
            info.confirmedPeriods[numberConfirmedPeriods].lockedValue = _lockedValue;
        } else {
            info.confirmedPeriods.push(ConfirmedPeriodInfo(nextPeriod, _lockedValue));
        }
        info.numberConfirmedPeriods++;

        var currentPeriod = nextPeriod - 1;
        if (info.lastActivePeriod < currentPeriod) {
            info.downtime.push(Downtime(info.lastActivePeriod + 1, currentPeriod));
        }
        info.lastActivePeriod = nextPeriod;
    }

    /**
    * @notice Confirm activity for future period
    **/
    function confirmActivity() external onlyTokenOwner {
        var info = tokenInfo[msg.sender];
        var currentPeriod = getCurrentPeriod();
        var nextPeriod = currentPeriod + 1;

        if (info.numberConfirmedPeriods > 0 &&
            info.confirmedPeriods[info.numberConfirmedPeriods - 1].period >= nextPeriod) {
           return;
        }

        var lockedTokens = calculateLockedTokens(
            msg.sender, false, getLockedTokens(msg.sender), 1);
        confirmActivity(lockedTokens);
    }

    /**
    * @notice Mint tokens for sender for previous periods if he locked his tokens and confirmed activity
    **/
    function mint() external onlyTokenOwner {
        var previousPeriod = getCurrentPeriod().sub(1);
        var info = tokenInfo[msg.sender];
        var numberPeriodsForMinting = info.numberConfirmedPeriods;
        require(numberPeriodsForMinting > 0 &&
            info.confirmedPeriods[0].period <= previousPeriod);

        var currentLockedValue = getLockedTokens(msg.sender);
        var allLockedPeriods = calculateLockedPeriods(
            msg.sender,
            info.confirmedPeriods[numberPeriodsForMinting - 1].lockedValue)
            .add(numberPeriodsForMinting);
        var decimals = info.decimals;

        if (info.confirmedPeriods[numberPeriodsForMinting - 1].period > previousPeriod) {
            numberPeriodsForMinting--;
        }
        if (info.confirmedPeriods[numberPeriodsForMinting - 1].period > previousPeriod) {
            numberPeriodsForMinting--;
        }

        uint256 reward = 0;
        uint256 amount = 0;
        for(uint i = 0; i < numberPeriodsForMinting; ++i) {
            var period = info.confirmedPeriods[i].period;
            var lockedValue = info.confirmedPeriods[i].lockedValue;
            allLockedPeriods--;
            (amount, decimals) = mint(
                previousPeriod,
                lockedValue,
                lockedPerPeriod[period],
                allLockedPeriods,
                decimals);
            reward = reward.add(amount);
            // TODO remove
            if (address(policyManager) != 0x0) {
                policyManager.updateReward(msg.sender, period);
            }
        }
        info.value = info.value.add(reward);
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
        external constant returns (address stop, uint256 shift)
    {
        require(_periods > 0);
        var currentPeriod = getCurrentPeriod();
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

    /**
    * @notice Set policy manager address
    **/
    function setPolicyManager(PolicyManager _policyManager) onlyOwner {
        require(_policyManager.escrow() == address(this));
        policyManager = _policyManager;
    }

    /**
    * @dev Get info about downtime periods
    * @param _owner Tokens owner
    * @param _index Index in array of downtime periods
    **/
    function getDowntimePeriods(address _owner, uint256 _index)
        public constant returns (uint256 startPeriod, uint256 endPeriod)
    {
        var period = tokenInfo[msg.sender].downtime[_index];
        startPeriod = period.startPeriod;
        endPeriod = period.endPeriod;
    }

    /**
    * @dev Get size of downtime periods array
    **/
    function getDowntimePeriodsLength(address _owner)
        public constant returns (uint256)
    {
        return tokenInfo[msg.sender].downtime.length;
    }

    /**
    * @dev Get last active period
    **/
    function getLastActivePeriod(address _owner)
        public constant returns (uint256)
    {
        return tokenInfo[msg.sender].lastActivePeriod;
    }
}
