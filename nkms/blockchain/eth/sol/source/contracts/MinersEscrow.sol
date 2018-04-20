pragma solidity ^0.4.18;


import "zeppelin/token/ERC20/SafeERC20.sol";
import "zeppelin/math/Math.sol";
import "./lib/AdditionalMath.sol";
import "contracts/Issuer.sol";

/**
* @notice PolicyManager interface
**/
contract PolicyManagerInterface {
    function updateReward(address _node, uint256 _period) external;
    function escrow() public view returns (address);
}


/**
* @notice Contract holds and locks nodes tokens.self._solidity_source_dir
Each node that lock its tokens will receive some compensation
**/
contract MinersEscrow is Issuer {
    using SafeERC20 for NuCypherKMSToken;
    using AdditionalMath for uint256;

    event Deposited(address indexed owner, uint256 value, uint256 periods);
    event Locked(address indexed owner, uint256 value, uint256 releaseRate);
    event LockSwitched(address indexed owner, bool release);
    event Withdrawn(address indexed owner, uint256 value);
    event ActivityConfirmed(address indexed owner, uint256 indexed period, uint256 value);
    event Mined(address indexed owner, uint256 indexed period, uint256 value);

    enum MinerInfoField {
        MinersLength,
        Miner,
        Value,
        Decimals,
        LockedValue,
        Release,
        MaxReleasePeriods,
        ReleaseRate,
        ConfirmedPeriodsLength,
        ConfirmedPeriod,
        ConfirmedPeriodLockedValue,
        LastActivePeriod,
        DowntimeLength,
        DowntimeStartPeriod,
        DowntimeEndPeriod,
        MinerIdsLength,
        MinerId
    }

    struct ConfirmedPeriodInfo {
        uint256 period;
        uint256 lockedValue;
    }

    struct Downtime {
        uint256 startPeriod;
        uint256 endPeriod;
    }

    struct MinerInfo {
        uint256 value;
        uint256 decimals;
        uint256 lockedValue;
        bool release;
        uint256 maxReleasePeriods;
        uint256 releaseRate;
        // periods that confirmed but not yet mined
        ConfirmedPeriodInfo[] confirmedPeriods;
        // downtime
        uint256 lastActivePeriod;
        Downtime[] downtime;
        bytes32[] minerIds;
    }

    uint256 constant MAX_PERIODS = 3;
    uint256 constant MAX_OWNERS = 50000;
    uint256 constant RESERVED_PERIOD = 0;

    mapping (address => MinerInfo) minerInfo;
    address[] miners;

    mapping (uint256 => uint256) public lockedPerPeriod;
    uint256 public minReleasePeriods;
    uint256 public minAllowableLockedTokens;
    uint256 public maxAllowableLockedTokens;
    PolicyManagerInterface public policyManager;

    /**
    * @notice Constructor sets address of token contract and coefficients for mining
    * @param _token Token contract
    * @param _hoursPerPeriod Size of period in hours
    * @param _miningCoefficient Mining coefficient
    * @param _minReleasePeriods Min amount of periods during which tokens will be released
    * @param _lockedPeriodsCoefficient Locked blocks coefficient
    * @param _awardedPeriods Max periods that will be additionally awarded
    * @param _minAllowableLockedTokens Min amount of tokens that can be locked
    * @param _maxAllowableLockedTokens Max amount of tokens that can be locked
    **/
    function MinersEscrow(
        NuCypherKMSToken _token,
        uint256 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint256 _awardedPeriods,
        uint256 _minReleasePeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens
    )
        public
        Issuer(
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
        maxAllowableLockedTokens = _maxAllowableLockedTokens;
    }

    /**
    * @dev Checks that sender exists in contract
    **/
    modifier onlyTokenOwner()
    {
        require(minerInfo[msg.sender].value > 0);
        _;
    }

    /**
    * @notice Get locked tokens value for owner in current period
    * @param _owner Tokens owner
    **/
    function getLockedTokens(address _owner)
        public view returns (uint256)
    {
        uint256 currentPeriod = getCurrentPeriod();
        MinerInfo storage info = minerInfo[_owner];

        // no confirmed periods, so current period may be release period
        if (info.confirmedPeriods.length == 0) {
            uint256 lockedValue = info.lockedValue;
        } else {
            uint256 i = info.confirmedPeriods.length - 1;
            ConfirmedPeriodInfo storage confirmedPeriod = info.confirmedPeriods[i];
            // last confirmed period is current period
            if (confirmedPeriod.period == currentPeriod) {
                return confirmedPeriod.lockedValue;
            // last confirmed period is previous periods, so current period may be release period
            } else if (confirmedPeriod.period < currentPeriod) {
                lockedValue = confirmedPeriod.lockedValue;
            // penultimate confirmed period is previous or current period, so get its lockedValue
            } else if (info.confirmedPeriods.length > 1) {
                return info.confirmedPeriods[info.confirmedPeriods.length - 2].lockedValue;
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
    function getAllLockedTokens() public view returns (uint256) {
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
        internal view returns (uint256)
    {
        MinerInfo storage info = minerInfo[_owner];
        if ((_forceRelease || info.release) && _periods != 0) {
            uint256 unlockedTokens = _periods.mul(info.releaseRate);
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
        public view returns (uint256)
    {
        require(_periods > 0);
        uint256 currentPeriod = getCurrentPeriod();
        uint256 nextPeriod = currentPeriod.add(_periods);

        MinerInfo storage info = minerInfo[_owner];
        if (info.confirmedPeriods.length > 0 &&
            info.confirmedPeriods[info.confirmedPeriods.length - 1].period >= currentPeriod) {
            ConfirmedPeriodInfo storage confirmedPeriod =
                info.confirmedPeriods[info.confirmedPeriods.length - 1];
            uint256 lockedTokens = confirmedPeriod.lockedValue;
            uint256 period = confirmedPeriod.period;
        } else {
            lockedTokens = getLockedTokens(_owner);
            period = currentPeriod;
        }
        uint256 periods = nextPeriod.sub(period);

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
        internal view returns (uint256)
    {
        MinerInfo storage info = minerInfo[_owner];
        return _lockedTokens.divCeil(info.releaseRate).sub(uint(1));
    }

    /**

    * @notice Pre-deposit tokens
    * @param _owners Tokens owners
    * @param _values Amount of token to deposit for each owner
    * @param _periods Amount of periods during which tokens will be unlocked for each owner
    **/
    function preDeposit(address[] _owners, uint256[] _values, uint256[] _periods)
        public isInitialized onlyOwner
    {
        require(_owners.length != 0 &&
            miners.length.add(_owners.length) <= MAX_OWNERS &&
            _owners.length == _values.length &&
            _owners.length == _periods.length);
        uint256 currentPeriod = getCurrentPeriod();
        uint256 allValue = 0;

        for (uint256 i = 0; i < _owners.length; i++) {
            address owner = _owners[i];
            uint256 value = _values[i];
            uint256 periods = _periods[i];
            MinerInfo storage info = minerInfo[owner];
            require(info.value == 0 &&
                value >= minAllowableLockedTokens &&
                value <= maxAllowableLockedTokens &&
                periods >= minReleasePeriods);
            // TODO optimize
            miners.push(owner);
            info.lastActivePeriod = currentPeriod;
            info.value = value;
            info.lockedValue = value;
            info.maxReleasePeriods = periods;
            info.releaseRate = Math.max256(value.divCeil(periods), 1);
            info.release = false;
            allValue = allValue.add(value);
            Deposited(owner, value, periods);
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
        MinerInfo storage info = minerInfo[msg.sender];
        if (minerInfo[msg.sender].value == 0) {
            require(miners.length < MAX_OWNERS);
            miners.push(msg.sender);
            info.lastActivePeriod = getCurrentPeriod();
        }
        info.value = info.value.add(_value);
        token.safeTransferFrom(msg.sender, address(this), _value);
        lock(_value, _periods);
        Deposited(msg.sender, _value, _periods);
    }

    /**
    * @notice Lock some tokens or increase lock
    * @param _value Amount of tokens which should lock
    * @param _periods Amount of periods during which tokens will be unlocked
    **/
    function lock(uint256 _value, uint256 _periods) public onlyTokenOwner {
        require(_value != 0 || _periods != 0);

        uint256 lockedTokens = calculateLockedTokens(msg.sender, 1);
        MinerInfo storage info = minerInfo[msg.sender];
        require(_value <= token.balanceOf(address(this)) &&
            _value <= info.value.sub(lockedTokens));

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
        require(info.lockedValue <= maxAllowableLockedTokens);

        confirmActivity(info.lockedValue);
        Locked(msg.sender, info.lockedValue, info.releaseRate);
        mint();
    }

    /**
    * @notice Switch lock
    **/
    function switchLock() public onlyTokenOwner {
        MinerInfo storage info = minerInfo[msg.sender];
        info.release = !info.release;
        LockSwitched(msg.sender, info.release);
    }

    /**
    * @notice Withdraw available amount of tokens back to owner
    * @param _value Amount of token to withdraw
    **/
    function withdraw(uint256 _value) public onlyTokenOwner {
        MinerInfo storage info = minerInfo[msg.sender];
        // TODO optimize
        uint256 lockedTokens = Math.max256(calculateLockedTokens(msg.sender, 1),
            getLockedTokens(msg.sender));
        require(_value <= token.balanceOf(address(this)) &&
            _value <= info.value.sub(lockedTokens));
        info.value -= _value;
        token.safeTransfer(msg.sender, _value);
        Withdrawn(msg.sender, _value);
    }

    /**
    * @notice Confirm activity for future period
    * @param _lockedValue Locked tokens in future period
    **/
    function confirmActivity(uint256 _lockedValue) internal {
        require(_lockedValue > 0);
        MinerInfo storage info = minerInfo[msg.sender];
        uint256 nextPeriod = getCurrentPeriod() + 1;

        if (info.confirmedPeriods.length > 0 &&
            info.confirmedPeriods[info.confirmedPeriods.length - 1].period == nextPeriod) {
            ConfirmedPeriodInfo storage confirmedPeriod =
                info.confirmedPeriods[info.confirmedPeriods.length - 1];
            lockedPerPeriod[nextPeriod] = lockedPerPeriod[nextPeriod]
                .add(_lockedValue.sub(confirmedPeriod.lockedValue));
            confirmedPeriod.lockedValue = _lockedValue;
            ActivityConfirmed(msg.sender, nextPeriod, _lockedValue);
            return;
        }

//        require(info.confirmedPeriods.length < MAX_PERIODS);
        lockedPerPeriod[nextPeriod] = lockedPerPeriod[nextPeriod]
            .add(_lockedValue);
        info.confirmedPeriods.push(ConfirmedPeriodInfo(nextPeriod, _lockedValue));

        uint256 currentPeriod = nextPeriod - 1;
        if (info.lastActivePeriod < currentPeriod) {
            info.downtime.push(Downtime(info.lastActivePeriod + 1, currentPeriod));
        }
        info.lastActivePeriod = nextPeriod;
        ActivityConfirmed(msg.sender, nextPeriod, _lockedValue);
    }

    /**
    * @notice Confirm activity for future period and mine for previous period
    **/
    function confirmActivity() external onlyTokenOwner {
        mint();
        MinerInfo storage info = minerInfo[msg.sender];
        uint256 currentPeriod = getCurrentPeriod();
        uint256 nextPeriod = currentPeriod + 1;

        if (info.confirmedPeriods.length > 0 &&
            info.confirmedPeriods[info.confirmedPeriods.length - 1].period >= nextPeriod) {
           return;
        }

        uint256 lockedTokens = calculateLockedTokens(
            msg.sender, false, getLockedTokens(msg.sender), 1);
        confirmActivity(lockedTokens);
    }

    /**
    * @notice Mint tokens for sender for previous periods if he locked his tokens and confirmed activity
    **/
    function mint() public onlyTokenOwner {
        uint256 previousPeriod = getCurrentPeriod().sub(uint(1));
        MinerInfo storage info = minerInfo[msg.sender];
        uint256 numberPeriodsForMinting = info.confirmedPeriods.length;
        if (numberPeriodsForMinting == 0 || info.confirmedPeriods[0].period > previousPeriod) {
            return;
        }

        uint256 currentLockedValue = getLockedTokens(msg.sender);
        ConfirmedPeriodInfo storage last = info.confirmedPeriods[numberPeriodsForMinting - 1];
        uint256 allLockedPeriods = last.lockedValue
            .divCeil(info.releaseRate)
            .sub(uint(1))
            .add(numberPeriodsForMinting);

        if (last.period > previousPeriod) {
            numberPeriodsForMinting--;
        }
        if (info.confirmedPeriods[numberPeriodsForMinting - 1].period > previousPeriod) {
            numberPeriodsForMinting--;
        }

        uint256 reward = 0;
        for(uint i = 0; i < numberPeriodsForMinting; ++i) {
            uint256 amount;
            uint256 period = info.confirmedPeriods[i].period;
            uint256 lockedValue = info.confirmedPeriods[i].lockedValue;
            allLockedPeriods--;
            (amount, info.decimals) = mint(
                previousPeriod,
                lockedValue,
                lockedPerPeriod[period],
                allLockedPeriods,
                info.decimals);
            reward = reward.add(amount);
            // TODO remove if
            if (address(policyManager) != 0x0) {
                policyManager.updateReward(msg.sender, period);
            }
        }
        info.value = info.value.add(reward);
        // Copy not minted periods
        for (i = 0; i < info.confirmedPeriods.length - numberPeriodsForMinting; i++) {
            info.confirmedPeriods[i] = info.confirmedPeriods[numberPeriodsForMinting + i];
        }
        info.confirmedPeriods.length -= numberPeriodsForMinting;

        // Update lockedValue for current period
        info.lockedValue = currentLockedValue;
        Mined(msg.sender, previousPeriod, reward);
    }

    /**
    * @notice Fixed-step in cumulative sum
    * @param _startIndex Starting point
    * @param _delta How much to step
    * @param _periods Amount of periods to get locked tokens
    *
             _startIndex
                v
      |-------->*--------------->*---->*------------->|
                |                      ^
                |                      stopIndex
                |
                |       _delta
                |---------------------------->|
                |
                |                       shift
                |                      |----->|
    **/
    function findCumSum(uint256 _startIndex, uint256 _delta, uint256 _periods)
        external view returns (address stop, uint256 stopIndex, uint256 shift)
    {
        require(_periods > 0);
        uint256 currentPeriod = getCurrentPeriod();
        uint256 distance = 0;

        for (uint256 i = _startIndex; i < miners.length; i++) {
            address current = miners[i];
            MinerInfo storage info = minerInfo[current];
            if (info.confirmedPeriods.length == 0) {
                continue;
            }
            ConfirmedPeriodInfo storage confirmedPeriod =
                info.confirmedPeriods[info.confirmedPeriods.length - 1];
            if (confirmedPeriod.period == currentPeriod) {
                uint256 lockedTokens = calculateLockedTokens(
                    current,
                    true,
                    confirmedPeriod.lockedValue,
                    _periods);
            } else if (info.confirmedPeriods.length > 1 &&
                info.confirmedPeriods[info.confirmedPeriods.length - 2].period == currentPeriod) {
                lockedTokens = calculateLockedTokens(
                    current,
                    true,
                    confirmedPeriod.lockedValue,
                    _periods - 1);
            } else {
                continue;
            }

            if (_delta < distance + lockedTokens) {
                stop = current;
                stopIndex = i;
                shift = _delta - distance;
                break;
            } else {
                distance += lockedTokens;
            }
        }
    }

    /**
    * @notice Set policy manager address
    **/
    function setPolicyManager(PolicyManagerInterface _policyManager) external onlyOwner {
        require(address(policyManager) == 0x0 &&
            _policyManager.escrow() == address(this));
        policyManager = _policyManager;
    }

    /**
    * @notice Set miner id
    **/
    function setMinerId(bytes32 _minerId) public {
        MinerInfo storage info = minerInfo[msg.sender];
        info.minerIds.push(_minerId);
    }

    /**
    * @notice Get information about miner
    * @dev This get method reduces size of bytecode compared with multiple get methods or public modifiers
    * @param _field Field to get
    * @param _miner Address of miner
    * @param _index Index of array
    **/
    function getMinerInfo(MinerInfoField _field, address _miner, uint256 _index)
        public view returns (bytes32)
    {
        if (_field == MinerInfoField.MinersLength) {
            return bytes32(miners.length);
        } else if (_field == MinerInfoField.Miner) {
            return bytes32(miners[_index]);
        }
        MinerInfo storage info = minerInfo[_miner];
        if (_field == MinerInfoField.Value) {
            return bytes32(info.value);
        } else if (_field == MinerInfoField.Decimals) {
            return bytes32(info.decimals);
        } else if (_field == MinerInfoField.LockedValue) {
            return bytes32(info.lockedValue);
        } else if (_field == MinerInfoField.Release) {
            return info.release ? bytes32(1) : bytes32(0);
        } else if (_field == MinerInfoField.MaxReleasePeriods) {
            return bytes32(info.maxReleasePeriods);
        } else if (_field == MinerInfoField.ReleaseRate) {
            return bytes32(info.releaseRate);
        } else if (_field == MinerInfoField.ConfirmedPeriodsLength) {
            return bytes32(info.confirmedPeriods.length);
        } else if (_field == MinerInfoField.ConfirmedPeriod) {
            return bytes32(info.confirmedPeriods[_index].period);
        } else if (_field == MinerInfoField.ConfirmedPeriodLockedValue) {
            return bytes32(info.confirmedPeriods[_index].lockedValue);
        } else if (_field == MinerInfoField.LastActivePeriod) {
            return bytes32(info.lastActivePeriod);
        } else if (_field == MinerInfoField.DowntimeLength) {
            return bytes32(info.downtime.length);
        } else if (_field == MinerInfoField.DowntimeStartPeriod) {
            return bytes32(info.downtime[_index].startPeriod);
        } else if (_field == MinerInfoField.DowntimeEndPeriod) {
            return bytes32(info.downtime[_index].endPeriod);
        } else if (_field == MinerInfoField.MinerIdsLength) {
            return bytes32(info.minerIds.length);
        } else if (_field == MinerInfoField.MinerId) {
            return bytes32(info.minerIds[_index]);
        }
    }

    function verifyState(address _testTarget) public onlyOwner {
        super.verifyState(_testTarget);
        require(uint256(delegateGet(_testTarget, "minReleasePeriods()")) ==
            minReleasePeriods);
        require(uint256(delegateGet(_testTarget, "minAllowableLockedTokens()")) ==
            minAllowableLockedTokens);
        require(uint256(delegateGet(_testTarget, "maxAllowableLockedTokens()")) ==
            maxAllowableLockedTokens);
        require(address(delegateGet(_testTarget, "policyManager()")) == address(policyManager));
        require(uint256(delegateGet(_testTarget, "lockedPerPeriod(uint256)",
            bytes32(RESERVED_PERIOD))) == lockedPerPeriod[RESERVED_PERIOD]);

        require(uint256(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
            bytes32(uint256(MinerInfoField.MinersLength)), 0x0, 0)) == miners.length);
        if (miners.length == 0) {
            return;
        }
        address minerAddress = miners[0];
        bytes32 miner = bytes32(minerAddress);
        require(address(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
            bytes32(uint8(MinerInfoField.Miner)), 0x0, 0)) == minerAddress);
        MinerInfo storage info = minerInfo[minerAddress];
        require(uint256(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
            bytes32(uint8(MinerInfoField.Value)), miner, 0)) == info.value);
        require(uint256(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
            bytes32(uint8(MinerInfoField.Decimals)), miner, 0)) == info.decimals);
        require(uint256(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
            bytes32(uint8(MinerInfoField.LockedValue)), miner, 0)) == info.lockedValue);
        require(((delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
            bytes32(uint8(MinerInfoField.Release)), miner, 0)) == bytes32(1)) == info.release);
        require(uint256(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
            bytes32(uint8(MinerInfoField.MaxReleasePeriods)), miner, 0)) == info.maxReleasePeriods);
        require(uint256(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
            bytes32(uint8(MinerInfoField.ReleaseRate)), miner, 0)) == info.releaseRate);
        require(uint256(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
            bytes32(uint8(MinerInfoField.ConfirmedPeriodsLength)), miner, 0)) == info.confirmedPeriods.length);
        for (uint256 i = 0; i < info.confirmedPeriods.length; i++) {
            ConfirmedPeriodInfo storage confirmedPeriod = info.confirmedPeriods[i];
            require(uint256(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
                bytes32(uint8(MinerInfoField.ConfirmedPeriod)), miner, bytes32(i))) == confirmedPeriod.period);
            require(uint256(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
                bytes32(uint8(MinerInfoField.ConfirmedPeriodLockedValue)), miner, bytes32(i))) ==
                confirmedPeriod.lockedValue);
        }
        require(uint256(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
            bytes32(uint8(MinerInfoField.LastActivePeriod)), miner, 0)) == info.lastActivePeriod);
        require(uint256(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
            bytes32(uint8(MinerInfoField.DowntimeLength)), miner, 0)) == info.downtime.length);
        for (i = 0; i < info.downtime.length && i < 10; i++) {
            Downtime storage downtime = info.downtime[i];
            require(uint256(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
                bytes32(uint8(MinerInfoField.DowntimeStartPeriod)), miner, bytes32(i))) == downtime.startPeriod);
            require(uint256(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
                bytes32(uint8(MinerInfoField.DowntimeEndPeriod)), miner, bytes32(i))) == downtime.endPeriod);
        }
        require(uint256(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
            bytes32(uint8(MinerInfoField.MinerIdsLength)), miner, 0)) == info.minerIds.length);
        for (i = 0; i < info.minerIds.length && i < 10; i++) {
            require(delegateGet(_testTarget, "getMinerInfo(uint8,address,uint256)",
                bytes32(uint8(MinerInfoField.MinerId)), miner, bytes32(i)) == info.minerIds[i]);
        }
    }

    function finishUpgrade(address _target) public onlyOwner {
        super.finishUpgrade(_target);
        MinersEscrow escrow = MinersEscrow(_target);
        policyManager = escrow.policyManager();
        minReleasePeriods = escrow.minReleasePeriods();
        minAllowableLockedTokens = escrow.minAllowableLockedTokens();
        maxAllowableLockedTokens = escrow.maxAllowableLockedTokens();

        // Create fake period
        lockedPerPeriod[RESERVED_PERIOD] = 111;
    }
}
