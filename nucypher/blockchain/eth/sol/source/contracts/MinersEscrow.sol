pragma solidity ^0.5.3;


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
* @notice MiningAdjudicator interface
**/
contract MiningAdjudicatorInterface {
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
    event Slashed(address indexed miner, uint256 penalty, address indexed investigator, uint256 reward);
    event ReStakeSet(address indexed miner, bool reStake);
    event ReStakeLocked(address indexed miner, uint16 lockUntilPeriod);
    event WorkerSet(address indexed miner, address indexed worker, uint16 indexed startPeriod);

    struct SubStakeInfo {
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
        * confirmActivity() method invokes mint() method so there can only be two confirmed
        * periods that are not yet mined: the current and the next periods.
        * Periods are not stored in order due to storage savings;
        * So, each time values of both variables need to be checked.
        * The EMPTY_CONFIRMED_PERIOD constant is used as a placeholder for removed values
        */
        uint16 confirmedPeriod1;
        uint16 confirmedPeriod2;
        bool reStake;
        uint16 lockReStakeUntilPeriod;
        // if the miner is the worker himself, then the address is zero
        address worker;
        // period when worker was set
        uint16 workerStartPeriod;
        // downtime
        uint16 lastActivePeriod;
        Downtime[] pastDowntime;
        SubStakeInfo[] subStakes;
    }

    /*
    * Used as removed value for confirmedPeriod1(2).
    * Non zero value decreases gas usage in some executions of confirmActivity() method
    * but increases gas usage in mint() method. In both cases confirmActivity()
    * with one execution of mint() method consume the same amount of gas
    */
    uint16 public constant EMPTY_CONFIRMED_PERIOD = 0;
    // used only for upgrading
    uint16 constant RESERVED_PERIOD = 0;
    uint16 constant MAX_CHECKED_VALUES = 5;
    // to prevent high gas consumption in loops for slashing
    uint16 public constant MAX_SUB_STAKES = 30;
    uint16 constant MAX_UINT16 = 65535;

    mapping (address => MinerInfo) public minerInfo;
    address[] public miners;
    mapping (address => address) public workerToMiner;

    mapping (uint16 => uint256) public lockedPerPeriod;
    uint16 public minLockedPeriods;
    uint16 public minWorkerPeriods;
    uint256 public minAllowableLockedTokens;
    uint256 public maxAllowableLockedTokens;
    PolicyManagerInterface public policyManager;
    MiningAdjudicatorInterface public miningAdjudicator;

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
    * @param _minWorkerPeriods Min amount of periods while a worker can't be changed
    **/
    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint16 _rewardedPeriods,
        uint16 _minLockedPeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens,
        uint16 _minWorkerPeriods
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
        minWorkerPeriods = _minWorkerPeriods;
    }

    /**
    * @dev Checks the existence of a miner in the contract
    **/
    modifier onlyMiner()
    {
        require(minerInfo[msg.sender].value > 0);
        _;
    }

    //------------------------Initialization------------------------
    /**
    * @notice Set policy manager address
    **/
    function setPolicyManager(PolicyManagerInterface _policyManager) external onlyOwner {
        require(address(policyManager) == address(0), "Policy manager can be set only once");
        require(_policyManager.escrow() == address(this),
            "This escrow must be the escrow for the new policy manager");
        policyManager = _policyManager;
    }

    /**
    * @notice Set mining adjudicator address
    **/
    function setMiningAdjudicator(MiningAdjudicatorInterface _miningAdjudicator) external onlyOwner {
        require(address(miningAdjudicator) == address(0), "Adjudicator can be set only once");
        require(_miningAdjudicator.escrow() == address(this),
            "This escrow must be the escrow for the new adjudicator");
        miningAdjudicator = _miningAdjudicator;
    }

    //------------------------Main getters------------------------
    /**
    * @notice Get all tokens belonging to the miner
    **/
    function getAllTokens(address _miner) public view returns (uint256) {
        return minerInfo[_miner].value;
    }

    /**
    * @notice Get the start period. Use in the calculation of the last period of the sub stake
    * @param _info Miner structure
    * @param _currentPeriod Current period
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
    * @notice Get the last period of the sub stake
    * @param _subStake Sub stake structure
    * @param _startPeriod Pre-calculated start period
    **/
    function getLastPeriodOfSubStake(SubStakeInfo storage _subStake, uint16 _startPeriod)
        internal view returns (uint16)
    {
        return _subStake.lastPeriod != 0 ? _subStake.lastPeriod : _startPeriod.add16(_subStake.periods);
    }

    /**
    * @notice Get the last period of the sub stake
    * @param _miner Miner
    * @param _index Stake index
    **/
    function getLastPeriodOfSubStake(address _miner, uint256 _index)
        public view returns (uint16)
    {
        MinerInfo storage info = minerInfo[_miner];
        require(_index < info.subStakes.length);
        SubStakeInfo storage subStake = info.subStakes[_index];
        uint16 startPeriod = getStartPeriod(info, getCurrentPeriod());
        return getLastPeriodOfSubStake(subStake, startPeriod);
    }


    /**
    * @notice Get the value of locked tokens for a miner in a specified period
    * @dev Information may be incorrect for mined or unconfirmed surpassed period
    * @param _info Miner structure
    * @param _currentPeriod Current period
    * @param _period Next period
    **/
    function getLockedTokens(MinerInfo storage _info, uint16 _currentPeriod, uint16 _period)
        internal view returns (uint256 lockedValue)
    {
        uint16 startPeriod = getStartPeriod(_info, _currentPeriod);
        for (uint256 i = 0; i < _info.subStakes.length; i++) {
            SubStakeInfo storage subStake = _info.subStakes[i];
            if (subStake.firstPeriod <= _period &&
                getLastPeriodOfSubStake(subStake, startPeriod) >= _period) {
                lockedValue = lockedValue.add(subStake.lockedValue);
            }
        }
    }

    /**
    * @notice Get the value of locked tokens for a miner in a future period
    * @param _miner Miner
    * @param _periods Amount of periods that will be added to the current period
    **/
    function getLockedTokens(address _miner, uint16 _periods)
        public view returns (uint256 lockedValue)
    {
        MinerInfo storage info = minerInfo[_miner];
        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod.add16(_periods);
        return getLockedTokens(info, currentPeriod, nextPeriod);
    }

    /**
    * @notice Get the value of locked tokens for a miner in a previous period
    * @dev Information may be incorrect for mined or unconfirmed surpassed period
    * @param _miner Miner
    * @param _periods Amount of periods that will be subtracted from the current period
    **/
    function getLockedTokensInPast(address _miner, uint16 _periods)
        public view returns (uint256 lockedValue)
    {
        MinerInfo storage info = minerInfo[_miner];
        uint16 currentPeriod = getCurrentPeriod();
        uint16 previousPeriod = currentPeriod.sub16(_periods);
        return getLockedTokens(info, currentPeriod, previousPeriod);
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
    * @notice Get the value of locked tokens for active miners in (getCurrentPeriod() + _periods) period
    * @param _periods Amount of periods for locked tokens calculation
    **/
    function getAllLockedTokens(uint16 _periods)
        external view returns (uint256 lockedTokens)
    {
        require(_periods > 0);
        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod.add16(_periods);
        for (uint256 i = 0; i < miners.length; i++) {
            address miner = miners[i];
            MinerInfo storage info = minerInfo[miner];
            if (info.confirmedPeriod1 != currentPeriod &&
                info.confirmedPeriod2 != currentPeriod) {
                continue;
            }
            lockedTokens = lockedTokens.add(getLockedTokens(info, currentPeriod, nextPeriod));
        }
    }

    /**
    * @notice Checks if `reStake` parameter is available for changing
    * @param _miner Miner
    **/
    function isReStakeLocked(address _miner) public view returns (bool) {
        return getCurrentPeriod() < minerInfo[_miner].lockReStakeUntilPeriod;
    }

    /**
    * @notice Get worker using miner's address
    **/
    function getWorkerByMiner(address _miner) public view returns (address) {
        MinerInfo storage info = minerInfo[_miner];
        // specified address is not a miner
        if (minerInfo[_miner].value == 0) {
            return address(0);
        }
        if (info.worker == address(0)) {
            return _miner;
        }
        return info.worker;
    }

    /**
    * @notice Get miner using worker's address
    **/
    function getMinerByWorker(address _worker) public view returns (address) {
        address miner = workerToMiner[_worker];
        if (miner != address(0)) {
            return miner;
        }
        // check if worker is miner: worker has stake and didn't set the worker value
        MinerInfo storage info = minerInfo[_worker];
        if (info.value != 0 && info.worker == address(0)) {
            return _worker;
        }
        return address(0);
    }

    //------------------------Main methods------------------------
    /**
    * @notice Set worker
    * @param _worker Worker address
    **/
    function setWorker(address _worker) public onlyMiner {
        require(_worker != address(0), "Worker's address must not be empty");
        require(msg.sender != tx.origin, "Only user of an intermediary contract can set a worker");

        uint16 currentPeriod = getCurrentPeriod();
        MinerInfo storage info = minerInfo[msg.sender];

        require(_worker != info.worker, "Specified worker is already set for this miner");
        require(currentPeriod >= info.workerStartPeriod.add16(minWorkerPeriods),
            "Not enough time has passed since the previous setting worker");
        require(workerToMiner[_worker] == address(0), "Specified worker is already in use");
        require(minerInfo[_worker].value == 0, "Specified worker is an another miner");

        // remove relation between the old worker and the miner
        if (info.worker != address(0)) {
            workerToMiner[info.worker] = address(0);
        }
        info.worker = _worker;
        info.workerStartPeriod = currentPeriod;
        workerToMiner[_worker] = msg.sender;
        emit WorkerSet(msg.sender, _worker, currentPeriod);
    }

    /**
    * @notice Set `reStake` parameter. If true then all mining reward will be added to locked stake
    * Only if this parameter is not locked
    * @param _reStake Value for parameter
    **/
    function setReStake(bool _reStake) public isInitialized {
        require(!isReStakeLocked(msg.sender));
        MinerInfo storage info = minerInfo[msg.sender];
        if (info.reStake == _reStake) {
            return;
        }
        info.reStake = _reStake;
        emit ReStakeSet(msg.sender, _reStake);
    }

    /**
    * @notice Lock `reStake` parameter. Only if this parameter is not locked
    * @param _lockReStakeUntilPeriod Can't change `reStake` value until this period
    **/
    function lockReStake(uint16 _lockReStakeUntilPeriod) public isInitialized {
        require(!isReStakeLocked(msg.sender) &&
            _lockReStakeUntilPeriod > getCurrentPeriod());
        minerInfo[msg.sender].lockReStakeUntilPeriod = _lockReStakeUntilPeriod;
        emit ReStakeLocked(msg.sender, _lockReStakeUntilPeriod);
    }

    /**
    * @notice Pre-deposit tokens
    * @param _miners Miners
    * @param _values Amount of tokens to deposit for each miner
    * @param _periods Amount of periods during which tokens will be locked for each miner
    **/
    function preDeposit(address[] memory _miners, uint256[] memory _values, uint16[] memory _periods)
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
            require(info.subStakes.length == 0 &&
                value >= minAllowableLockedTokens &&
                value <= maxAllowableLockedTokens &&
                periods >= minLockedPeriods);
            require(workerToMiner[miner] == address(0) || workerToMiner[miner] == info.worker,
                "A miner can't be a worker for another miner");
            miners.push(miner);
            policyManager.register(miner, currentPeriod);
            info.value = value;
            info.subStakes.push(SubStakeInfo(currentPeriod.add16(1), 0, periods, value));
            allValue = allValue.add(value);
            emit Deposited(miner, value, periods);
        }

        token.safeTransferFrom(msg.sender, address(this), allValue);
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
        bytes calldata /* _extraData */
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
        require(workerToMiner[_miner] == address(0) || workerToMiner[_miner] == info.worker,
            "A miner can't be a worker for another miner");
        // initial stake of the miner
        if (info.subStakes.length == 0) {
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

        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod.add16(1);
        MinerInfo storage info = minerInfo[_miner];
        uint256 lockedTokens = getLockedTokens(info, currentPeriod, nextPeriod);
        require(_value.add(lockedTokens) <= info.value &&
            _value.add(lockedTokens) <= maxAllowableLockedTokens);

        if (info.confirmedPeriod1 != nextPeriod && info.confirmedPeriod2 != nextPeriod) {
            saveSubStake(info, nextPeriod, 0, _periods, _value);
        } else {
            // next period is confirmed
            saveSubStake(info, nextPeriod, 0, _periods - 1, _value);
            lockedPerPeriod[nextPeriod] = lockedPerPeriod[nextPeriod].add(_value);
            emit ActivityConfirmed(_miner, nextPeriod, _value);
        }

        emit Locked(_miner, _value, nextPeriod, _periods);
    }

    /**
    * @notice Save sub stake. First tries to override inactive sub stake
    * @dev Inactive sub stake means that last period of sub stake has been surpassed and already mined
    * @param _info Miner structure
    * @param _firstPeriod First period of the sub stake
    * @param _lastPeriod Last period of the sub stake
    * @param _periods Duration of the sub stake in periods
    * @param _lockedValue Amount of locked tokens
    **/
    function saveSubStake(
        MinerInfo storage _info,
        uint16 _firstPeriod,
        uint16 _lastPeriod,
        uint16 _periods,
        uint256 _lockedValue
    )
        internal
    {
        for (uint256 i = 0; i < _info.subStakes.length; i++) {
            SubStakeInfo storage subStake = _info.subStakes[i];
            if (subStake.lastPeriod != 0 &&
                (_info.confirmedPeriod1 == EMPTY_CONFIRMED_PERIOD ||
                subStake.lastPeriod < _info.confirmedPeriod1) &&
                (_info.confirmedPeriod2 == EMPTY_CONFIRMED_PERIOD ||
                subStake.lastPeriod < _info.confirmedPeriod2))
            {
                subStake.firstPeriod = _firstPeriod;
                subStake.lastPeriod = _lastPeriod;
                subStake.periods = _periods;
                subStake.lockedValue = _lockedValue;
                return;
            }
        }
        require(_info.subStakes.length < MAX_SUB_STAKES);
        _info.subStakes.push(SubStakeInfo(_firstPeriod, _lastPeriod, _periods, _lockedValue));
    }

    /**
    * @notice Divide sub stake into two parts
    * @param _index Index of the sub stake
    * @param _newValue New sub stake value
    * @param _periods Amount of periods for extending sub stake
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
            _index < info.subStakes.length);
        SubStakeInfo storage subStake = info.subStakes[_index];
        uint16 currentPeriod = getCurrentPeriod();
        uint16 startPeriod = getStartPeriod(info, currentPeriod);
        uint16 lastPeriod = getLastPeriodOfSubStake(subStake, startPeriod);
        require(lastPeriod >= currentPeriod);

        uint256 oldValue = subStake.lockedValue;
        subStake.lockedValue = oldValue.sub(_newValue);
        require(subStake.lockedValue >= minAllowableLockedTokens);
        saveSubStake(info, subStake.firstPeriod, 0, subStake.periods.add16(_periods), _newValue);
        // if the next period is confirmed and
        // old sub stake is finishing in the current period then update confirmation
        if (lastPeriod == currentPeriod && startPeriod > currentPeriod) {
            lockedPerPeriod[startPeriod] = lockedPerPeriod[startPeriod].add(_newValue);
            emit ActivityConfirmed(msg.sender, startPeriod, _newValue);
        }
        emit Divided(msg.sender, oldValue, lastPeriod, _newValue, _periods);
        emit Locked(msg.sender, _newValue, subStake.firstPeriod, subStake.periods + _periods);
    }

    /**
    * @notice Withdraw available amount of tokens to miner
    * @param _value Amount of tokens to withdraw
    **/
    function withdraw(uint256 _value) public onlyMiner {
        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod.add16(1);
        MinerInfo storage info = minerInfo[msg.sender];
        // the max locked tokens in most cases will be in the current period
        // but when the miner stakes more then we should use the next period
        uint256 lockedTokens = Math.max(getLockedTokens(info, currentPeriod, nextPeriod),
            getLockedTokens(info, currentPeriod, currentPeriod));
        require(_value <= token.balanceOf(address(this)) &&
            _value <= info.value.sub(lockedTokens));
        info.value -= _value;
        token.safeTransfer(msg.sender, _value);
        emit Withdrawn(msg.sender, _value);
    }

    /**
    * @notice Confirm activity for the next period and mine for the previous period
    **/
    function confirmActivity() external onlyMiner {
        require(getWorkerByMiner(msg.sender) == tx.origin, "Only worker can confirm activity");

        uint16 lastActivePeriod = getLastActivePeriod(msg.sender);
        mint(msg.sender);
        MinerInfo storage info = minerInfo[msg.sender];
        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod.add16(1);

        // the period has already been confirmed
        if (info.confirmedPeriod1 == nextPeriod ||
            info.confirmedPeriod2 == nextPeriod) {
            return;
        }

        uint256 lockedTokens = getLockedTokens(info, currentPeriod, nextPeriod);
        require(lockedTokens > 0);
        lockedPerPeriod[nextPeriod] = lockedPerPeriod[nextPeriod].add(lockedTokens);

        if (info.confirmedPeriod1 == EMPTY_CONFIRMED_PERIOD) {
            info.confirmedPeriod1 = nextPeriod;
        } else {
            info.confirmedPeriod2 = nextPeriod;
        }

        for (uint256 index = 0; index < info.subStakes.length; index++) {
            SubStakeInfo storage subStake = info.subStakes[index];
            if (subStake.lastPeriod == 0 && subStake.periods > 1) {
                subStake.periods--;
            } else if (subStake.lastPeriod == 0 && subStake.periods == 1) {
                subStake.periods = 0;
                subStake.lastPeriod = nextPeriod;
            }
        }

        // miner was inactive for several periods
        if (lastActivePeriod < currentPeriod) {
            info.pastDowntime.push(Downtime(lastActivePeriod + 1, currentPeriod));
        }
        emit ActivityConfirmed(msg.sender, nextPeriod, lockedTokens);
    }

    /**
    * @notice Mint tokens for previous periods if miner locked their tokens and confirmed activity
    **/
    function mint() external onlyMiner {
        // save last active period to the storage if both periods will be empty after minting
        // because we won't be able to calculate last active period
        // see getLastActivePeriod(address)
        MinerInfo storage info = minerInfo[msg.sender];
        uint16 previousPeriod = getCurrentPeriod().sub16(1);
        if (info.confirmedPeriod1 <= previousPeriod &&
            info.confirmedPeriod2 <= previousPeriod &&
            (info.confirmedPeriod1 != EMPTY_CONFIRMED_PERIOD ||
            info.confirmedPeriod2 != EMPTY_CONFIRMED_PERIOD))
        {
            info.lastActivePeriod = AdditionalMath.max16(info.confirmedPeriod1, info.confirmedPeriod2);
        }
        mint(msg.sender);
    }

    /**
    * @notice Mint tokens for previous periods if miner locked their tokens and confirmed activity
    * @param _miner Miner
    **/
    function mint(address _miner) internal {
        uint16 currentPeriod = getCurrentPeriod();
        uint16 previousPeriod = currentPeriod.sub16(1);
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

        uint16 startPeriod = getStartPeriod(info, currentPeriod);
        uint256 reward = 0;
        if (info.confirmedPeriod1 != EMPTY_CONFIRMED_PERIOD &&
            info.confirmedPeriod1 < info.confirmedPeriod2) {
            reward = reward.add(mint(_miner, info, 1, currentPeriod, startPeriod));
        } else if (info.confirmedPeriod2 != EMPTY_CONFIRMED_PERIOD &&
            info.confirmedPeriod2 < info.confirmedPeriod1) {
            reward = reward.add(mint(_miner, info, 2, currentPeriod, startPeriod));
        }
        if (info.confirmedPeriod2 <= previousPeriod &&
            info.confirmedPeriod2 > info.confirmedPeriod1) {
            reward = reward.add(mint(_miner, info, 2, currentPeriod, startPeriod));
        } else if (info.confirmedPeriod1 <= previousPeriod &&
            info.confirmedPeriod1 > info.confirmedPeriod2) {
            reward = reward.add(mint(_miner, info, 1, currentPeriod, startPeriod));
        }

        info.value = info.value.add(reward);
        emit Mined(_miner, previousPeriod, reward);
    }

    /**
    * @notice Calculate reward for one period
    * @param _miner Miner's address
    * @param _info Miner structure
    * @param _confirmedPeriodNumber Number of confirmed period (1 or 2)
    * @param _currentPeriod Current period
    * @param _startPeriod Pre-calculated start period
    **/
    function mint(
        address _miner,
        MinerInfo storage _info,
        uint8 _confirmedPeriodNumber,
        uint16 _currentPeriod,
        uint16 _startPeriod
    )
        internal returns (uint256 reward)
    {
        uint16 mintingPeriod = _confirmedPeriodNumber == 1 ? _info.confirmedPeriod1 : _info.confirmedPeriod2;
        for (uint256 i = 0; i < _info.subStakes.length; i++) {
            SubStakeInfo storage subStake =  _info.subStakes[i];
            uint16 lastPeriod = getLastPeriodOfSubStake(subStake, _startPeriod);
            if (subStake.firstPeriod <= mintingPeriod && lastPeriod >= mintingPeriod) {
                uint256 subStakeReward = mint(
                    _currentPeriod,
                    subStake.lockedValue,
                    lockedPerPeriod[mintingPeriod],
                    lastPeriod.sub16(mintingPeriod));
                reward = reward.add(subStakeReward);
                if (_info.reStake) {
                    subStake.lockedValue = subStake.lockedValue.add(subStakeReward);
                }
            }
        }
        policyManager.updateReward(_miner, mintingPeriod);
        if (_confirmedPeriodNumber == 1) {
            _info.confirmedPeriod1 = EMPTY_CONFIRMED_PERIOD;
        } else {
            _info.confirmedPeriod2 = EMPTY_CONFIRMED_PERIOD;
        }
        if (!_info.reStake) {
            return reward;
        }
        if (_confirmedPeriodNumber == 1 &&
            _info.confirmedPeriod2 != EMPTY_CONFIRMED_PERIOD) {
            lockedPerPeriod[_info.confirmedPeriod2] = lockedPerPeriod[_info.confirmedPeriod2].add(reward);
        } else if (_confirmedPeriodNumber == 2 &&
            _info.confirmedPeriod1 != EMPTY_CONFIRMED_PERIOD) {
            lockedPerPeriod[_info.confirmedPeriod1] = lockedPerPeriod[_info.confirmedPeriod1].add(reward);
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
    function sample(uint256[] calldata _points, uint16 _periods)
        external view returns (address[] memory result)
    {
        require(_periods > 0 && _points.length > 0);
        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod.add16(_periods);
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
                sumOfLockedTokens = sumOfLockedTokens.add(getLockedTokens(info, currentPeriod, nextPeriod));
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

    //-------------------------Slashing-------------------------
    /**
    * @notice Slash the miner's stake and reward the investigator
    * @param _miner Miner's address
    * @param _penalty Penalty
    * @param _investigator Investigator
    * @param _reward Reward for the investigator
    **/
    function slashMiner(
        address _miner,
        uint256 _penalty,
        address _investigator,
        uint256 _reward
    )
        public
    {
        require(msg.sender == address(miningAdjudicator));
        require(_penalty > 0);
        MinerInfo storage info = minerInfo[_miner];
        if (info.value <= _penalty) {
            _penalty = info.value;
        }
        info.value -= _penalty;
        if (_reward > _penalty) {
            _reward = _penalty;
        }

        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod.add16(1);
        uint16 startPeriod = getStartPeriod(info, currentPeriod);

        (uint256 currentLock, uint256 nextLock, uint256 currentAndNextLock, uint256 shortestSubStakeIndex) =
            getLockedTokensAndShortestSubStake(info, currentPeriod, nextPeriod, startPeriod);

        // Decrease the stake if amount of locked tokens in the current period more than miner has
        uint256 lockedTokens = currentLock + currentAndNextLock;
        if (info.value < lockedTokens) {
           decreaseSubStakes(info, lockedTokens - info.value, currentPeriod, startPeriod, shortestSubStakeIndex);
        }
        // Decrease the stake if amount of locked tokens in the next period more than miner has
        if (nextLock > 0) {
            lockedTokens = nextLock + currentAndNextLock -
                (currentAndNextLock > info.value ? currentAndNextLock - info.value : 0);
            if (info.value < lockedTokens) {
               decreaseSubStakes(info, lockedTokens - info.value, nextPeriod, startPeriod, MAX_SUB_STAKES);
            }
        }

        emit Slashed(_miner, _penalty, _investigator, _reward);
        _penalty -= _reward;
        if (_penalty > 0) {
            unMint(_penalty);
        }
        // TODO change to withdrawal pattern
        if (_reward > 0) {
            token.safeTransfer(_investigator, _reward);
        }
    }

    /**
    * @notice Get the value of locked tokens for a miner in the current and the next period
    * and find the shortest sub stake
    * @param _info Miner structure
    * @param _currentPeriod Current period
    * @param _nextPeriod Next period
    * @param _startPeriod Pre-calculated start period
    * @return currentLock Amount of tokens that locked in the current period and unlocked in the next period
    * @return nextLock Amount of tokens that locked in the next period and not locked in the current period
    * @return currentAndNextLock Amount of tokens that locked in the current period and in the next period
    * @return shortestSubStakeIndex Index of the shortest sub stake
    **/
    function getLockedTokensAndShortestSubStake(
        MinerInfo storage _info,
        uint16 _currentPeriod,
        uint16 _nextPeriod,
        uint16 _startPeriod
    )
        internal view returns (
            uint256 currentLock,
            uint256 nextLock,
            uint256 currentAndNextLock,
            uint256 shortestSubStakeIndex
        )
    {
        uint16 minDuration = MAX_UINT16;
        uint16 minLastPeriod = MAX_UINT16;
        shortestSubStakeIndex = MAX_SUB_STAKES;
        for (uint256 i = 0; i < _info.subStakes.length; i++) {
            SubStakeInfo storage subStake = _info.subStakes[i];
            uint16 lastPeriod = getLastPeriodOfSubStake(subStake, _startPeriod);
            if (lastPeriod < subStake.firstPeriod) {
                continue;
            }
            if (subStake.firstPeriod <= _currentPeriod &&
                lastPeriod >= _nextPeriod) {
                currentAndNextLock = currentAndNextLock.add(subStake.lockedValue);
            } else if (subStake.firstPeriod <= _currentPeriod &&
                lastPeriod >= _currentPeriod) {
                currentLock = currentLock.add(subStake.lockedValue);
            } else if (subStake.firstPeriod <= _nextPeriod &&
                lastPeriod >= _nextPeriod) {
                nextLock = nextLock.add(subStake.lockedValue);
            }
            uint16 duration = lastPeriod.sub16(subStake.firstPeriod);
            if (subStake.firstPeriod <= _currentPeriod &&
                lastPeriod >= _currentPeriod &&
                (lastPeriod < minLastPeriod ||
                lastPeriod == minLastPeriod && duration < minDuration))
            {
                shortestSubStakeIndex = i;
                minDuration = duration;
                minLastPeriod = lastPeriod;
            }
        }
    }

    /**
    * @notice Decrease short sub stakes
    * @param _info Miner structure
    * @param _penalty Penalty rate
    * @param _decreasePeriod The period when the decrease begins
    * @param _startPeriod Pre-calculated start period
    * @param _shortestSubStakeIndex Index of the shortest period
    **/
    function decreaseSubStakes(
        MinerInfo storage _info,
        uint256 _penalty,
        uint16 _decreasePeriod,
        uint16 _startPeriod,
        uint256 _shortestSubStakeIndex
    )
        internal
    {
        SubStakeInfo storage shortestSubStake = _info.subStakes[0];
        uint16 minSubStakeLastPeriod = MAX_UINT16;
        uint16 minSubStakeDuration = MAX_UINT16;
        while(_penalty > 0) {
            if (_shortestSubStakeIndex < MAX_SUB_STAKES) {
                shortestSubStake = _info.subStakes[_shortestSubStakeIndex];
                minSubStakeLastPeriod = getLastPeriodOfSubStake(shortestSubStake, _startPeriod);
                minSubStakeDuration = minSubStakeLastPeriod.sub16(shortestSubStake.firstPeriod);
                _shortestSubStakeIndex = MAX_SUB_STAKES;
            } else {
                (shortestSubStake, minSubStakeDuration, minSubStakeLastPeriod) =
                    getShortestSubStake(_info, _decreasePeriod, _startPeriod);
            }
            if (minSubStakeDuration == MAX_UINT16) {
                break;
            }
            uint256 appliedPenalty = _penalty;
            if (_penalty < shortestSubStake.lockedValue) {
                shortestSubStake.lockedValue -= _penalty;
                saveOldSubStake(_info, shortestSubStake.firstPeriod, _penalty, _decreasePeriod);
                _penalty = 0;
            } else {
                shortestSubStake.lastPeriod = _decreasePeriod.sub16(1);
                _penalty -= shortestSubStake.lockedValue;
                appliedPenalty = shortestSubStake.lockedValue;
            }
            if (_info.confirmedPeriod1 >= _decreasePeriod &&
                _info.confirmedPeriod1 <= minSubStakeLastPeriod)
            {
                lockedPerPeriod[_info.confirmedPeriod1] -= appliedPenalty;
            }
            if (_info.confirmedPeriod2 >= _decreasePeriod &&
                _info.confirmedPeriod2 <= minSubStakeLastPeriod)
            {
                lockedPerPeriod[_info.confirmedPeriod2] -= appliedPenalty;
            }
        }
    }

    /**
    * @notice Get the shortest sub stake
    * @param _info Miner structure
    * @param _currentPeriod Current period
    * @param _startPeriod Pre-calculated start period
    * @return shortestSubStake The shortest sub stake
    * @return minSubStakeDuration Duration of the shortest sub stake
    * @return minSubStakeLastPeriod Last period of the shortest sub stake
    **/
    function getShortestSubStake(
        MinerInfo storage _info,
        uint16 _currentPeriod,
        uint16 _startPeriod
    )
        internal view returns (
            SubStakeInfo storage shortestSubStake,
            uint16 minSubStakeDuration,
            uint16 minSubStakeLastPeriod
        )
    {
        shortestSubStake = shortestSubStake;
        minSubStakeDuration = MAX_UINT16;
        minSubStakeLastPeriod = MAX_UINT16;
        for (uint256 i = 0; i < _info.subStakes.length; i++) {
            SubStakeInfo storage subStake = _info.subStakes[i];
            uint16 lastPeriod = getLastPeriodOfSubStake(subStake, _startPeriod);
            if (lastPeriod < subStake.firstPeriod) {
                continue;
            }
            uint16 duration = lastPeriod.sub16(subStake.firstPeriod);
            if (subStake.firstPeriod <= _currentPeriod &&
                lastPeriod >= _currentPeriod &&
                (lastPeriod < minSubStakeLastPeriod ||
                lastPeriod == minSubStakeLastPeriod && duration < minSubStakeDuration))
            {
                shortestSubStake = subStake;
                minSubStakeDuration = duration;
                minSubStakeLastPeriod = lastPeriod;
            }
        }
    }

    /**
    * @notice Save the old sub stake values to prevent decreasing reward for the previous period
    * @dev Saving happens only if the previous period is confirmed
    * @param _info Miner structure
    * @param _firstPeriod First period of the old sub stake
    * @param _lockedValue Locked value of the old sub stake
    * @param _currentPeriod Current period, when the old sub stake is already unlocked
    **/
    function saveOldSubStake(
        MinerInfo storage _info,
        uint16 _firstPeriod,
        uint256 _lockedValue,
        uint16 _currentPeriod
    )
        internal
    {
        // Check that the old sub stake should be saved
        bool oldConfirmedPeriod1 = _info.confirmedPeriod1 != EMPTY_CONFIRMED_PERIOD &&
            _info.confirmedPeriod1 < _currentPeriod;
        bool oldConfirmedPeriod2 = _info.confirmedPeriod2 != EMPTY_CONFIRMED_PERIOD &&
            _info.confirmedPeriod2 < _currentPeriod;
        bool crossConfirmedPeriod1 = oldConfirmedPeriod1 && _info.confirmedPeriod1 >= _firstPeriod;
        bool crossConfirmedPeriod2 = oldConfirmedPeriod2 && _info.confirmedPeriod2 >= _firstPeriod;
        if (!crossConfirmedPeriod1 && !crossConfirmedPeriod2) {
            return;
        }
        // Try to find already existent proper old sub stake
        uint16 previousPeriod = _currentPeriod.sub16(1);
        bool createNew = true;
        for (uint256 i = 0; i < _info.subStakes.length; i++) {
            SubStakeInfo storage subStake = _info.subStakes[i];
            if (subStake.lastPeriod == previousPeriod &&
                ((crossConfirmedPeriod1 ==
                (oldConfirmedPeriod1 && _info.confirmedPeriod1 >= subStake.firstPeriod)) &&
                (crossConfirmedPeriod2 ==
                (oldConfirmedPeriod2 && _info.confirmedPeriod2 >= subStake.firstPeriod))))
            {
                subStake.lockedValue += _lockedValue;
                createNew = false;
                break;
            }
        }
        if (createNew) {
            saveSubStake(_info, _firstPeriod, previousPeriod, 0, _lockedValue);
        }
    }

    //-------------Additional getters for miners info-------------
    /**
    * @notice Return the length of the array of miners
    **/
    function getMinersLength() public view returns (uint256) {
        return miners.length;
    }

    /**
    * @notice Return the length of the array of sub stakes
    **/
    function getSubStakesLength(address _miner) public view returns (uint256) {
        return minerInfo[_miner].subStakes.length;
    }

    /**
    * @notice Return the information about sub stake
    **/
    function getSubStakeInfo(address _miner, uint256 _index)
    // TODO change to structure when ABIEncoderV2 is released
//        public view returns (SubStakeInfo)
        public view returns (uint16 firstPeriod, uint16 lastPeriod, uint16 periods, uint256 lockedValue)
    {
        SubStakeInfo storage info = minerInfo[_miner].subStakes[_index];
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
    function delegateGetMinerInfo(address _target, bytes32 _miner)
        internal returns (MinerInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, "minerInfo(address)", 1, _miner, 0);
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get SubStakeInfo structure by delegatecall
    **/
    function delegateGetSubStakeInfo(address _target, bytes32 _miner, uint256 _index)
        internal returns (SubStakeInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(
            _target, "getSubStakeInfo(address,uint256)", 2, _miner, bytes32(_index));
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get Downtime structure by delegatecall
    **/
    function delegateGetPastDowntime(address _target, bytes32 _miner, uint256 _index)
        internal returns (Downtime memory result)
    {
        bytes32 memoryAddress = delegateGetData(
            _target, "getPastDowntime(address,uint256)", 2, _miner, bytes32(_index));
        assembly {
            result := memoryAddress
        }
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `verifyState`
    function verifyState(address _testTarget) public {
        super.verifyState(_testTarget);
        require(uint16(delegateGet(_testTarget, "minWorkerPeriods()")) == minWorkerPeriods);
        require(delegateGet(_testTarget, "minAllowableLockedTokens()") == minAllowableLockedTokens);
        require(delegateGet(_testTarget, "maxAllowableLockedTokens()") == maxAllowableLockedTokens);
        require(address(delegateGet(_testTarget, "policyManager()")) == address(policyManager));
        require(address(delegateGet(_testTarget, "miningAdjudicator()")) == address(miningAdjudicator));
        require(delegateGet(_testTarget, "lockedPerPeriod(uint16)",
            bytes32(bytes2(RESERVED_PERIOD))) == lockedPerPeriod[RESERVED_PERIOD]);
        require(address(delegateGet(_testTarget, "workerToMiner(address)", bytes32(0))) ==
            workerToMiner[address(0)]);

        require(delegateGet(_testTarget, "getMinersLength()") == miners.length);
        if (miners.length == 0) {
            return;
        }
        address minerAddress = miners[0];
        require(address(uint160(delegateGet(_testTarget, "miners(uint256)", 0))) == minerAddress);
        MinerInfo storage info = minerInfo[minerAddress];
        bytes32 miner = bytes32(uint256(minerAddress));
        MinerInfo memory infoToCheck = delegateGetMinerInfo(_testTarget, miner);
        require(infoToCheck.value == info.value &&
            infoToCheck.confirmedPeriod1 == info.confirmedPeriod1 &&
            infoToCheck.confirmedPeriod2 == info.confirmedPeriod2 &&
            infoToCheck.reStake == info.reStake &&
            infoToCheck.lockReStakeUntilPeriod == info.lockReStakeUntilPeriod &&
            infoToCheck.lastActivePeriod == info.lastActivePeriod &&
            infoToCheck.worker == info.worker &&
            infoToCheck.workerStartPeriod == info.workerStartPeriod);

        require(delegateGet(_testTarget, "getPastDowntimeLength(address)", miner) ==
            info.pastDowntime.length);
        for (uint256 i = 0; i < info.pastDowntime.length && i < MAX_CHECKED_VALUES; i++) {
            Downtime storage downtime = info.pastDowntime[i];
            Downtime memory downtimeToCheck = delegateGetPastDowntime(_testTarget, miner, i);
            require(downtimeToCheck.startPeriod == downtime.startPeriod &&
                downtimeToCheck.endPeriod == downtime.endPeriod);
        }

        require(delegateGet(_testTarget, "getSubStakesLength(address)", miner) == info.subStakes.length);
        for (uint256 i = 0; i < info.subStakes.length && i < MAX_CHECKED_VALUES; i++) {
            SubStakeInfo storage subStakeInfo = info.subStakes[i];
            SubStakeInfo memory subStakeInfoToCheck = delegateGetSubStakeInfo(_testTarget, miner, i);
            require(subStakeInfoToCheck.firstPeriod == subStakeInfo.firstPeriod &&
                subStakeInfoToCheck.lastPeriod == subStakeInfo.lastPeriod &&
                subStakeInfoToCheck.periods == subStakeInfo.periods &&
                subStakeInfoToCheck.lockedValue == subStakeInfo.lockedValue);
        }

        if (info.worker != address(0)) {
            require(address(delegateGet(_testTarget, "workerToMiner(address)", bytes32(uint256(info.worker)))) ==
                workerToMiner[info.worker]);
        }
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `finishUpgrade`
    function finishUpgrade(address _target) public {
        super.finishUpgrade(_target);
        MinersEscrow escrow = MinersEscrow(_target);
        minLockedPeriods = escrow.minLockedPeriods();
        minAllowableLockedTokens = escrow.minAllowableLockedTokens();
        maxAllowableLockedTokens = escrow.maxAllowableLockedTokens();
        minWorkerPeriods = escrow.minWorkerPeriods();

        // Create fake period
        lockedPerPeriod[RESERVED_PERIOD] = 111;

        // Create fake worker
        workerToMiner[address(0)] = address(this);
    }
}
