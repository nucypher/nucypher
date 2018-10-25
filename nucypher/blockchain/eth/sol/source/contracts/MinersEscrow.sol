pragma solidity ^0.4.24;


import "zeppelin/token/ERC20/SafeERC20.sol";
import "contracts/Issuer.sol";


/**
* @notice PolicyManager interface
**/
contract PolicyManagerInterface {
    function register(address _node, uint16 _period) external;
    function updateReward(address _node, uint16 _period) external;
    function escrow() public view returns (address);
}


/**
* @notice Contract holds and locks miners tokens.
* Each miner that locks their tokens will receive some compensation
**/
contract MinersEscrow is Issuer {
    using SafeERC20 for NuCypherToken;
    using AdditionalMath for uint256;
    using AdditionalMath for uint16;

    event Deposited(address indexed miner, uint256 value, uint16 periods);
    event Locked(address indexed miner, uint256 value, uint16 firstPeriod, uint16 periods);
    event Divided(
        address indexed miner,
        uint256 oldValue,
        uint16 lastPeriod,
        uint256 newValue,
        uint16 periods
    );
    event Withdrawn(address indexed miner, uint256 value);
    event ActivityConfirmed(address indexed miner, uint16 indexed period, uint256 value);
    event Mined(address indexed miner, uint16 indexed period, uint256 value);

    struct StakeInfo {
        uint16 firstPeriod;
        uint16 lastPeriod;
        uint16 periods;
        uint256 lockedValue;
    }

    struct Downtime {
        uint16 startPeriod;
        uint16 endPeriod;
    }

    struct MinerInfo {
        uint256 value;
        /*
        * Stores periods that are confirmed but not yet mined.
        * In order to optimize storage, only two values are used instead of an array.
        * lock() and confirmActivity() methods invoke the mint() method so there can only be two confirmed
        * periods that are not yet mined: the current and the next periods.
        * Periods are not stored in order due to storage savings;
        * So, each time values of both variables need to be checked.
        * The EMPTY_CONFIRMED_PERIOD constant is used as a placeholder for removed values
        */
        uint16 confirmedPeriod1;
        uint16 confirmedPeriod2;
        // downtime
        uint16 lastActivePeriod;
        Downtime[] pastDowntime;
        StakeInfo[] stakes;
    }

    /*
    * Used as removed value for confirmedPeriod1(2).
    * Non zero value decreases gas usage in some executions of confirmActivity() method
    * but increases gas usage in mint() method. In both cases confirmActivity()
    * with one execution of mint() method consume the same amount of gas
    */
    uint16 constant EMPTY_CONFIRMED_PERIOD = 0;
    uint16 constant RESERVED_PERIOD = 0;
    uint16 constant MAX_CHECKED_VALUES = 5;

    mapping (address => MinerInfo) public minerInfo;
    address[] public miners;

    mapping (uint16 => uint256) public lockedPerPeriod;
    uint16 public minLockedPeriods;
    uint256 public minAllowableLockedTokens;
    uint256 public maxAllowableLockedTokens;
    PolicyManagerInterface public policyManager;

    /**
    * @notice Constructor sets address of token contract and coefficients for mining
    * @param _token Token contract
    * @param _hoursPerPeriod Size of period in hours
    * @param _miningCoefficient Mining coefficient
    * @param _minLockedPeriods Min amount of periods during which tokens can be locked
    * @param _lockedPeriodsCoefficient Locked blocks coefficient
    * @param _rewardedPeriods Max periods that will be additionally rewarded
    * @param _minAllowableLockedTokens Min amount of tokens that can be locked
    * @param _maxAllowableLockedTokens Max amount of tokens that can be locked
    **/
    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint16 _rewardedPeriods,
        uint16 _minLockedPeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens
    )
        public
        Issuer(
            _token,
            _hoursPerPeriod,
            _miningCoefficient,
            _lockedPeriodsCoefficient,
            _rewardedPeriods
        )
    {
        // constant `1` in the expression `_minLockedPeriods > 1` uses to simplify the `lock` method
        require(_minLockedPeriods > 1 && _maxAllowableLockedTokens != 0);
        minLockedPeriods = _minLockedPeriods;
        minAllowableLockedTokens = _minAllowableLockedTokens;
        maxAllowableLockedTokens = _maxAllowableLockedTokens;
    }

    /**
    * @dev Checks the existence of a miner in the contract
    **/
    modifier onlyMiner()
    {
        require(minerInfo[msg.sender].value > 0);
        _;
    }

    /**
    * @notice Set policy manager address
    **/
    // TODO maybe combine this with initialization in Issuer?
    function setPolicyManager(PolicyManagerInterface _policyManager) external onlyOwner {
        require(address(policyManager) == 0x0 &&
            _policyManager.escrow() == address(this));
        policyManager = _policyManager;
    }

    /**
    * @notice Get the start period. Use in the calculation of the last period of the stake
    **/
    function getStartPeriod(MinerInfo storage _info, uint16 _currentPeriod)
        internal view returns (uint16)
    {
        // if the next period (after current) is confirmed
        if (_info.confirmedPeriod1 > _currentPeriod || _info.confirmedPeriod2 > _currentPeriod) {
            return _currentPeriod.add16(1);
        }
        return _currentPeriod;
    }

    /**
    * @notice Get the last period of the stake
    **/
    function getLastPeriodOfStake(StakeInfo storage _stake, uint16 _startPeriod)
        internal view returns (uint16)
    {
        return _stake.lastPeriod != 0 ? _stake.lastPeriod : _startPeriod.add16(_stake.periods);
    }

    /**
    * @notice Get the last period of the stake
    * @param _miner Miner
    * @param _index Stake index
    **/
    function getLastPeriodOfStake(address _miner, uint256 _index)
        public view returns (uint16)
    {
        MinerInfo storage info = minerInfo[_miner];
        require(_index < info.stakes.length);
        StakeInfo storage stake = info.stakes[_index];
        uint16 startPeriod = getStartPeriod(info, getCurrentPeriod());
        return getLastPeriodOfStake(stake, startPeriod);
    }

    /**
    * @notice Get the value of locked tokens for a miner in a future period
    * @param _miner Miner
    * @param _periods Amount of periods to calculate locked tokens
    **/
    function getLockedTokens(address _miner, uint16 _periods)
        public view returns (uint256 lockedValue)
    {
        uint16 startPeriod = getCurrentPeriod();
        uint16 nextPeriod = startPeriod.add16(_periods);
        MinerInfo storage info = minerInfo[_miner];
        startPeriod = getStartPeriod(info, startPeriod);

        for (uint256 i = 0; i < info.stakes.length; i++) {
            StakeInfo storage stake = info.stakes[i];
            if (stake.firstPeriod <= nextPeriod &&
                getLastPeriodOfStake(stake, startPeriod) >= nextPeriod) {
                lockedValue = lockedValue.add(stake.lockedValue);
            }
        }
    }

    /**
    * @notice Get the value of locked tokens for a miner in the current period
    * @param _miner Miner
    **/
    function getLockedTokens(address _miner)
        public view returns (uint256)
    {
        return getLockedTokens(_miner, 0);
    }

    /**
    * @notice Pre-deposit tokens
    * @param _miners Miners
    * @param _values Amount of tokens to deposit for each miner
    * @param _periods Amount of periods during which tokens will be locked for each miner
    **/
    function preDeposit(address[] _miners, uint256[] _values, uint16[] _periods)
        public isInitialized
    {
        require(_miners.length != 0 &&
            _miners.length == _values.length &&
            _miners.length == _periods.length);
        uint16 currentPeriod = getCurrentPeriod();
        uint256 allValue = 0;

        for (uint256 i = 0; i < _miners.length; i++) {
            address miner = _miners[i];
            uint256 value = _values[i];
            uint16 periods = _periods[i];
            MinerInfo storage info = minerInfo[miner];
            require(info.stakes.length == 0 &&
                value >= minAllowableLockedTokens &&
                value <= maxAllowableLockedTokens &&
                periods >= minLockedPeriods);
            miners.push(miner);
            policyManager.register(miner, currentPeriod);
            info.value = value;
            info.stakes.push(StakeInfo(currentPeriod.add16(1), 0, periods, value));
            allValue = allValue.add(value);
            emit Deposited(miner, value, periods);
        }

        token.safeTransferFrom(msg.sender, address(this), allValue);
    }

    /**
    * @notice Get the last active miner's period
    * @param _miner Miner
    **/
    function getLastActivePeriod(address _miner) public view returns (uint16) {
        MinerInfo storage info = minerInfo[_miner];
        if (info.confirmedPeriod1 != EMPTY_CONFIRMED_PERIOD ||
            info.confirmedPeriod2 != EMPTY_CONFIRMED_PERIOD) {
            return AdditionalMath.max16(info.confirmedPeriod1, info.confirmedPeriod2);
        }
        return info.lastActivePeriod;
    }

    /**
    * @notice Implementation of the receiveApproval(address,uint256,address,bytes) method
    * (see NuCypherToken contract). Deposit all tokens that were approved to transfer
    * @param _from Miner
    * @param _value Amount of tokens to deposit
    * @param _tokenContract Token contract address
    * @notice (param _extraData) Amount of periods during which tokens will be locked
    **/
    function receiveApproval(
        address _from,
        uint256 _value,
        address _tokenContract,
        bytes /* _extraData */
    )
        external
    {
        require(_tokenContract == address(token) && msg.sender == address(token));
        // copy first 32 bytes from _extraData. Position is calculated as
        // 4 bytes method signature plus 32 * 3 bytes for previous params and
        // addition 32 bytes to skip _extraData pointer
        uint256 payloadSize;
        uint256 payload;
        assembly {
            payloadSize := calldataload(0x84)
            payload := calldataload(0xA4)
        }
        payload = payload >> 8*(32 - payloadSize);
        deposit(_from, _value, uint16(payload));
    }

    /**
    * @notice Deposit tokens
    * @param _value Amount of tokens to deposit
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function deposit(uint256 _value, uint16 _periods) public {
        deposit(msg.sender, _value, _periods);
    }

    /**
    * @notice Deposit tokens
    * @param _miner Miner
    * @param _value Amount of tokens to deposit
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function deposit(address _miner, uint256 _value, uint16 _periods) internal isInitialized {
        require(_value != 0);
        MinerInfo storage info = minerInfo[_miner];
        // initial stake of the miner
        if (info.stakes.length == 0) {
            miners.push(_miner);
            policyManager.register(_miner, getCurrentPeriod());
        }
        info.value = info.value.add(_value);
        token.safeTransferFrom(_miner, address(this), _value);
        lock(_miner, _value, _periods);
        emit Deposited(_miner, _value, _periods);
    }

    /**
    * @notice Lock some tokens as a stake
    * @param _value Amount of tokens which will be locked
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function lock(uint256 _value, uint16 _periods) public onlyMiner {
        lock(msg.sender, _value, _periods);
    }

    /**
    * @notice Lock some tokens as a stake
    * @param _miner Miner
    * @param _value Amount of tokens which will be locked
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function lock(address _miner, uint256 _value, uint16 _periods) internal {
        require(_value <= token.balanceOf(address(this)) &&
            _value >= minAllowableLockedTokens &&
            _periods >= minLockedPeriods);
        uint16 lastActivePeriod = getLastActivePeriod(_miner);
        mint(_miner);

        uint256 lockedTokens = getLockedTokens(_miner, 1);
        MinerInfo storage info = minerInfo[_miner];
        require(_value.add(lockedTokens) <= info.value &&
            _value.add(lockedTokens) <= maxAllowableLockedTokens);

        uint16 nextPeriod = getCurrentPeriod().add16(1);
        if (info.confirmedPeriod1 != nextPeriod && info.confirmedPeriod2 != nextPeriod) {
            info.stakes.push(StakeInfo(nextPeriod, 0, _periods, _value));
        } else {
            info.stakes.push(StakeInfo(nextPeriod, 0, _periods - 1, _value));
        }

        confirmActivity(_miner, _value + lockedTokens, _value, lastActivePeriod);
        emit Locked(_miner, _value, nextPeriod, _periods);
    }

    /**
    * @notice Divide stake into two parts
    * @param _index Index of the stake
    * @param _newValue New stake value
    * @param _periods Amount of periods for extending stake
    **/
    function divideStake(
        uint256 _index,
        uint256 _newValue,
        uint16 _periods
    )
        public onlyMiner
    {
        MinerInfo storage info = minerInfo[msg.sender];
        require(_newValue >= minAllowableLockedTokens &&
            _periods > 0 &&
            _index < info.stakes.length);
        StakeInfo storage stake = info.stakes[_index];
        uint16 currentPeriod = getCurrentPeriod();
        uint16 startPeriod = getStartPeriod(info, currentPeriod);
        uint16 lastPeriod = getLastPeriodOfStake(stake, startPeriod);
        require(lastPeriod >= currentPeriod);

        uint256 oldValue = stake.lockedValue;
        stake.lockedValue = oldValue.sub(_newValue);
        require(stake.lockedValue >= minAllowableLockedTokens);
        info.stakes.push(StakeInfo(stake.firstPeriod, 0, stake.periods.add16(_periods), _newValue));
        // if the next period is confirmed and old stake is finishing in the current period then rerun confirmActivity
        if (lastPeriod == currentPeriod && startPeriod > currentPeriod) {
            confirmActivity(msg.sender, _newValue, _newValue, 0);
        }
        emit Divided(msg.sender, oldValue, lastPeriod, _newValue, _periods);
        emit Locked(msg.sender, _newValue, stake.firstPeriod, stake.periods + _periods);
    }

    /**
    * @notice Withdraw available amount of tokens to miner
    * @param _value Amount of tokens to withdraw
    **/
    function withdraw(uint256 _value) public onlyMiner {
        MinerInfo storage info = minerInfo[msg.sender];
        // the max locked tokens in most cases will be in the current period
        // but when the miner stakes more then we should use the next period
        uint256 lockedTokens = Math.max256(getLockedTokens(msg.sender, 1),
            getLockedTokens(msg.sender, 0));
        require(_value <= token.balanceOf(address(this)) &&
            _value <= info.value.sub(lockedTokens));
        info.value -= _value;
        token.safeTransfer(msg.sender, _value);
        emit Withdrawn(msg.sender, _value);
    }

    /**
    * @notice Confirm activity for the next period
    * @param _miner Miner
    * @param _lockedValue Locked tokens in the next period
    * @param _additional Additional locked tokens in the next period.
    * Used only if the period has already been confirmed
    * @param _lastActivePeriod Last active period
    **/
    function confirmActivity(
        address _miner,
        uint256 _lockedValue,
        uint256 _additional,
        uint16 _lastActivePeriod
    ) internal {
        require(_lockedValue > 0);
        MinerInfo storage info = minerInfo[_miner];
        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod.add16(1);

        // update lockedValue if the period has already been confirmed
        if (info.confirmedPeriod1 == nextPeriod) {
            lockedPerPeriod[nextPeriod] = lockedPerPeriod[nextPeriod].add(_additional);
            emit ActivityConfirmed(_miner, nextPeriod, _additional);
            return;
        } else if (info.confirmedPeriod2 == nextPeriod) {
            lockedPerPeriod[nextPeriod] = lockedPerPeriod[nextPeriod].add(_additional);
            emit ActivityConfirmed(_miner, nextPeriod, _additional);
            return;
        }

        lockedPerPeriod[nextPeriod] = lockedPerPeriod[nextPeriod].add(_lockedValue);
        if (info.confirmedPeriod1 == EMPTY_CONFIRMED_PERIOD) {
            info.confirmedPeriod1 = nextPeriod;
        } else {
            info.confirmedPeriod2 = nextPeriod;
        }

        for (uint256 index = 0; index < info.stakes.length; index++) {
            StakeInfo storage stake = info.stakes[index];
            if (stake.periods > 1) {
                stake.periods--;
            } else if (stake.periods == 1) {
                stake.periods = 0;
                stake.lastPeriod = nextPeriod;
            }
        }

        // miner was inactive for several periods
        if (_lastActivePeriod < currentPeriod) {
            info.pastDowntime.push(Downtime(_lastActivePeriod + 1, currentPeriod));
        }
        emit ActivityConfirmed(_miner, nextPeriod, _lockedValue);
    }

    /**
    * @notice Confirm activity for the next period and mine for the previous period
    **/
    function confirmActivity() external onlyMiner {
        uint16 lastActivePeriod = getLastActivePeriod(msg.sender);
        mint(msg.sender);
        MinerInfo storage info = minerInfo[msg.sender];
        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod + 1;

        // the period has already been confirmed
        if (info.confirmedPeriod1 == nextPeriod ||
            info.confirmedPeriod2 == nextPeriod) {
            return;
        }

        uint256 lockedTokens = getLockedTokens(msg.sender, 1);
        confirmActivity(msg.sender, lockedTokens, 0, lastActivePeriod);
    }

    /**
    * @notice Mint tokens for previous periods if miner locked their tokens and confirmed activity
    **/
    function mint() external onlyMiner {
        // save last active period to the storage if only one period is confirmed
        // because after this minting confirmed periods can be empty and can't calculate period from them
        // see getLastActivePeriod(address)
        MinerInfo storage info = minerInfo[msg.sender];
        if (info.confirmedPeriod1 != EMPTY_CONFIRMED_PERIOD ||
            info.confirmedPeriod2 != EMPTY_CONFIRMED_PERIOD) {
            info.lastActivePeriod = AdditionalMath.max16(info.confirmedPeriod1, info.confirmedPeriod2);
        }
        mint(msg.sender);
    }

    /**
    * @notice Mint tokens for previous periods if miner locked their tokens and confirmed activity
    * @param _miner Miner
    **/
    function mint(address _miner) internal {
        uint16 startPeriod = getCurrentPeriod();
        uint16 previousPeriod = startPeriod.sub16(1);
        MinerInfo storage info = minerInfo[_miner];

        if (info.confirmedPeriod1 > previousPeriod &&
            info.confirmedPeriod2 > previousPeriod ||
            info.confirmedPeriod1 > previousPeriod &&
            info.confirmedPeriod2 == EMPTY_CONFIRMED_PERIOD ||
            info.confirmedPeriod2 > previousPeriod &&
            info.confirmedPeriod1 == EMPTY_CONFIRMED_PERIOD ||
            info.confirmedPeriod1 == EMPTY_CONFIRMED_PERIOD &&
            info.confirmedPeriod2 == EMPTY_CONFIRMED_PERIOD) {
            return;
        }

        uint16 first;
        uint16 last;
        if (info.confirmedPeriod1 > info.confirmedPeriod2) {
            last = info.confirmedPeriod1;
            first = info.confirmedPeriod2;
        } else {
            first = info.confirmedPeriod1;
            last = info.confirmedPeriod2;
        }

        startPeriod = getStartPeriod(info, startPeriod);
        uint256 reward = 0;
        if (info.confirmedPeriod1 != EMPTY_CONFIRMED_PERIOD &&
            info.confirmedPeriod1 < info.confirmedPeriod2) {
            reward = reward.add(mint(_miner, info, info.confirmedPeriod1, previousPeriod, startPeriod));
            info.confirmedPeriod1 = EMPTY_CONFIRMED_PERIOD;
        } else if (info.confirmedPeriod2 != EMPTY_CONFIRMED_PERIOD &&
            info.confirmedPeriod2 < info.confirmedPeriod1) {
            reward = reward.add(mint(_miner, info, info.confirmedPeriod2, previousPeriod, startPeriod));
            info.confirmedPeriod2 = EMPTY_CONFIRMED_PERIOD;
        }
        if (info.confirmedPeriod2 <= previousPeriod &&
            info.confirmedPeriod2 > info.confirmedPeriod1) {
            reward = reward.add(mint(_miner, info, info.confirmedPeriod2, previousPeriod, startPeriod));
            info.confirmedPeriod2 = EMPTY_CONFIRMED_PERIOD;
        } else if (info.confirmedPeriod1 <= previousPeriod &&
            info.confirmedPeriod1 > info.confirmedPeriod2) {
            reward = reward.add(mint(_miner, info, info.confirmedPeriod1, previousPeriod, startPeriod));
            info.confirmedPeriod1 = EMPTY_CONFIRMED_PERIOD;
        }

        info.value = info.value.add(reward);
        emit Mined(_miner, previousPeriod, reward);
    }

    /**
    * @notice Calculate reward for one period
    **/
    function mint(
        address _miner,
        MinerInfo storage _info,
        uint16 _period,
        uint16 _previousPeriod,
        uint16 _startPeriod
    )
        internal returns (uint256 reward)
    {
        for (uint256 i = 0; i < _info.stakes.length; i++) {
            StakeInfo storage stake =  _info.stakes[i];
            uint16 lastPeriod = getLastPeriodOfStake(stake, _startPeriod);
            if (stake.firstPeriod <= _period && lastPeriod >= _period) {
                reward = reward.add(mint(
                    _previousPeriod,
                    stake.lockedValue,
                    lockedPerPeriod[_period],
                    lastPeriod.sub16(_period)));
            }
        }
        policyManager.updateReward(_miner, _period);
    }

    /**
    * @notice Get the value of locked tokens for active miners in (getCurrentPeriod() + _periods) period
    * @param _periods Amount of periods for locked tokens calculation
    **/
    function getAllLockedTokens(uint16 _periods)
        external view returns (uint256 lockedTokens)
    {
        require(_periods > 0);
        uint16 currentPeriod = getCurrentPeriod();
        for (uint256 i = 0; i < miners.length; i++) {
            address miner = miners[i];
            MinerInfo storage info = minerInfo[miner];
            if (info.confirmedPeriod1 != currentPeriod &&
                info.confirmedPeriod2 != currentPeriod) {
                continue;
            }
            lockedTokens = lockedTokens.add(getLockedTokens(miner, _periods));
        }
    }

    /**
    * @notice Get active miners based on input points
    * @param _points Array of absolute values
    * @param _periods Amount of periods for locked tokens calculation
    *
    * @dev Sampling iterates over an array of miners and input points.
    * Each iteration checks if the current point is contained within the current miner stake.
    * If the point is greater than or equal to the current sum of stakes,
    * this miner is skipped and the sum is increased by the value of next miner's stake.
    * If a point is less than the current sum of stakes, then the current miner is appended to the resulting array.
    * Secondly, the sum of stakes is decreased by a point;
    * The next iteration will check the next point for the difference.
    * Only miners which confirmed the current period (in the previous period) are used.
    * If the number of points is more than the number of active miners with suitable stakes,
    * the last values in the resulting array will be zeros addresses.
    * The length of this array is always equal to the number of points.
    **/
    function sample(uint256[] _points, uint16 _periods)
        external view returns (address[] result)
    {
        require(_periods > 0 && _points.length > 0);
        uint16 currentPeriod = getCurrentPeriod();
        result = new address[](_points.length);

        uint256 pointIndex = 0;
        uint256 sumOfLockedTokens = 0;
        uint256 minerIndex = 0;
        bool addMoreTokens = true;
        while (minerIndex < miners.length && pointIndex < _points.length) {
            address currentMiner = miners[minerIndex];
            MinerInfo storage info = minerInfo[currentMiner];
            uint256 point = _points[pointIndex];
            if (info.confirmedPeriod1 != currentPeriod &&
                info.confirmedPeriod2 != currentPeriod) {
                minerIndex += 1;
                addMoreTokens = true;
                continue;
            }
            if (addMoreTokens) {
                sumOfLockedTokens = sumOfLockedTokens.add(getLockedTokens(currentMiner, _periods));
            }
            if (sumOfLockedTokens > point) {
                result[pointIndex] = currentMiner;
                sumOfLockedTokens -= point;
                pointIndex += 1;
                addMoreTokens = false;
            } else {
                minerIndex += 1;
                addMoreTokens = true;
            }
        }
    }

    // TODO complete
    function slashMiner(address _miner, uint256 _amount) public {
        revert("Not implemented yet");
    }

    //-------------Additional getters for miners info-------------
    /**
    * @notice Return the length of the array of miners
    **/
    function getMinersLength() public view returns (uint256) {
        return miners.length;
    }

    /**
    * @notice Return the length of the array of stakes
    **/
    function getStakesLength(address _miner) public view returns (uint256) {
        return minerInfo[_miner].stakes.length;
    }

    /**
    * @notice Return the information about stake
    **/
    function getStakeInfo(address _miner, uint256 _index)
    // TODO change to structure when ABIEncoderV2 is released
//        public view returns (StakeInfo)
        public view returns (uint16 firstPeriod, uint16 lastPeriod, uint16 periods, uint256 lockedValue)
    {
        StakeInfo storage info = minerInfo[_miner].stakes[_index];
        firstPeriod = info.firstPeriod;
        lastPeriod = info.lastPeriod;
        periods = info.periods;
        lockedValue = info.lockedValue;
    }

    /**
    * @notice Return the length of the array of past downtime
    **/
    function getPastDowntimeLength(address _miner) public view returns (uint256) {
        return minerInfo[_miner].pastDowntime.length;
    }

    /**
    * @notice Return the information about past downtime
    **/
    function  getPastDowntime(address _miner, uint256 _index)
    // TODO change to structure when ABIEncoderV2 is released
//        public view returns (Downtime)
        public view returns (uint16 startPeriod, uint16 endPeriod)
    {
        Downtime storage downtime = minerInfo[_miner].pastDowntime[_index];
        startPeriod = downtime.startPeriod;
        endPeriod = downtime.endPeriod;
    }


    //------------------------Upgradeable------------------------
    /**
    * @dev Get MinerInfo structure by delegatecall
    **/
    function delegateGetMinerInfo(address _target, address _miner)
        internal returns (MinerInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, "minerInfo(address)", 1, bytes32(_miner), 0);
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get StakeInfo structure by delegatecall
    **/
    function delegateGetStakeInfo(address _target, address _miner, uint256 _index)
        internal returns (StakeInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(
            _target, "getStakeInfo(address,uint256)", 2, bytes32(_miner), bytes32(_index));
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get Downtime structure by delegatecall
    **/
    function delegateGetPastDowntime(address _target, address _miner, uint256 _index)
        internal returns (Downtime memory result)
    {
        bytes32 memoryAddress = delegateGetData(
            _target, "getPastDowntime(address,uint256)", 2, bytes32(_miner), bytes32(_index));
        assembly {
            result := memoryAddress
        }
    }

    function verifyState(address _testTarget) public onlyOwner {
        super.verifyState(_testTarget);
        require(uint16(delegateGet(_testTarget, "minLockedPeriods()")) ==
            minLockedPeriods);
        require(uint256(delegateGet(_testTarget, "minAllowableLockedTokens()")) ==
            minAllowableLockedTokens);
        require(uint256(delegateGet(_testTarget, "maxAllowableLockedTokens()")) ==
            maxAllowableLockedTokens);
        require(address(delegateGet(_testTarget, "policyManager()")) == address(policyManager));
        require(uint256(delegateGet(_testTarget, "lockedPerPeriod(uint16)",
            bytes32(RESERVED_PERIOD))) == lockedPerPeriod[RESERVED_PERIOD]);

        require(uint256(delegateGet(_testTarget, "getMinersLength()")) == miners.length);
        if (miners.length == 0) {
            return;
        }
        address minerAddress = miners[0];
        bytes32 miner = bytes32(minerAddress);
        require(address(delegateGet(_testTarget, "miners(uint256)", 0)) == minerAddress);
        MinerInfo storage info = minerInfo[minerAddress];
        MinerInfo memory infoToCheck = delegateGetMinerInfo(_testTarget, minerAddress);
        require(infoToCheck.value == info.value &&
            infoToCheck.confirmedPeriod1 == info.confirmedPeriod1 &&
            infoToCheck.confirmedPeriod2 == info.confirmedPeriod2 &&
            infoToCheck.lastActivePeriod == info.lastActivePeriod);

        require(uint256(delegateGet(_testTarget, "getPastDowntimeLength(address)", miner)) ==
            info.pastDowntime.length);
        for (i = 0; i < info.pastDowntime.length && i < MAX_CHECKED_VALUES; i++) {
            Downtime storage downtime = info.pastDowntime[i];
            Downtime memory downtimeToCheck = delegateGetPastDowntime(_testTarget, minerAddress, i);
            require(downtimeToCheck.startPeriod == downtime.startPeriod &&
                downtimeToCheck.endPeriod == downtime.endPeriod);
        }

        require(uint256(delegateGet(_testTarget, "getStakesLength(address)", miner)) == info.stakes.length);
        for (uint256 i = 0; i < info.stakes.length && i < MAX_CHECKED_VALUES; i++) {
            StakeInfo storage stakeInfo = info.stakes[i];
            StakeInfo memory stakeInfoToCheck = delegateGetStakeInfo(_testTarget, minerAddress, i);
            require(stakeInfoToCheck.firstPeriod == stakeInfo.firstPeriod &&
                stakeInfoToCheck.lastPeriod == stakeInfo.lastPeriod &&
                stakeInfoToCheck.periods == stakeInfo.periods &&
                stakeInfoToCheck.lockedValue == stakeInfo.lockedValue);
        }
    }

    function finishUpgrade(address _target) public onlyOwner {
        super.finishUpgrade(_target);
        MinersEscrow escrow = MinersEscrow(_target);
        minLockedPeriods = escrow.minLockedPeriods();
        minAllowableLockedTokens = escrow.minAllowableLockedTokens();
        maxAllowableLockedTokens = escrow.maxAllowableLockedTokens();

        // Create fake period
        lockedPerPeriod[RESERVED_PERIOD] = 111;
    }
}
