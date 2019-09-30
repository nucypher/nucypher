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
* @notice Adjudicator interface
**/
contract AdjudicatorInterface {
    function escrow() public view returns (address);
}


/**
* @notice WorkLock interface
**/
contract WorkLockInterface {
    function escrow() public view returns (address);
}


/**
* @notice Contract holds and locks stakers tokens.
* Each staker that locks their tokens will receive some compensation
**/
contract StakingEscrow is Issuer {
    using SafeERC20 for NuCypherToken;
    using AdditionalMath for uint256;
    using AdditionalMath for uint16;

    event Deposited(address indexed staker, uint256 value, uint16 periods);
    event Locked(address indexed staker, uint256 value, uint16 firstPeriod, uint16 periods);
    event Divided(
        address indexed staker,
        uint256 oldValue,
        uint16 lastPeriod,
        uint256 newValue,
        uint16 periods
    );
    event Withdrawn(address indexed staker, uint256 value);
    event ActivityConfirmed(address indexed staker, uint16 indexed period, uint256 value);
    event Mined(address indexed staker, uint16 indexed period, uint256 value);
    event Slashed(address indexed staker, uint256 penalty, address indexed investigator, uint256 reward);
    event ReStakeSet(address indexed staker, bool reStake);
    event ReStakeLocked(address indexed staker, uint16 lockUntilPeriod);
    event WorkerSet(address indexed staker, address indexed worker, uint16 indexed startPeriod);
    event WorkMeasurementSet(address indexed staker, bool measureWork);

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

    struct StakerInfo {
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
        address worker;
        // period when worker was set
        uint16 workerStartPeriod;
        // last confirmed active period
        uint16 lastActivePeriod;
        Downtime[] pastDowntime;
        SubStakeInfo[] subStakes;
        bool measureWork;
        uint256 completedWork;
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

    mapping (address => StakerInfo) public stakerInfo;
    address[] public stakers;
    mapping (address => address) public workerToStaker;

    mapping (uint16 => uint256) public lockedPerPeriod;
    uint16 public minLockedPeriods;
    uint16 public minWorkerPeriods; // TODO: What's a good minimum time to allow stakers to change/unset worker? (#1073)
    uint256 public minAllowableLockedTokens;
    uint256 public maxAllowableLockedTokens;
    PolicyManagerInterface public policyManager;
    AdjudicatorInterface public adjudicator;
    WorkLockInterface public workLock;

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
    * @dev Checks the existence of a staker in the contract
    **/
    modifier onlyStaker()
    {
        require(stakerInfo[msg.sender].value > 0);
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
    * @notice Set adjudicator address
    **/
    function setAdjudicator(AdjudicatorInterface _adjudicator) external onlyOwner {
        require(address(adjudicator) == address(0), "Adjudicator can be set only once");
        require(_adjudicator.escrow() == address(this),
            "This escrow must be the escrow for the new adjudicator");
        adjudicator = _adjudicator;
    }

    /**
    * @notice Set worklock address
    **/
    function setWorkLock(WorkLockInterface _workLock) external onlyOwner {
        // Two-part require...
        require(address(workLock) == address(0) &&  // Can't workLock once it is set.
            _workLock.escrow() == address(this));  // This is the escrow for the new workLock.
        workLock = _workLock;
    }

    //------------------------Main getters------------------------
    /**
    * @notice Get all tokens belonging to the staker
    **/
    function getAllTokens(address _staker) public view returns (uint256) {
        return stakerInfo[_staker].value;
    }

    /**
    * @notice Get the start period. Use in the calculation of the last period of the sub stake
    * @param _info Staker structure
    * @param _currentPeriod Current period
    **/
    function getStartPeriod(StakerInfo storage _info, uint16 _currentPeriod)
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
    * @param _staker Staker
    * @param _index Stake index
    **/
    function getLastPeriodOfSubStake(address _staker, uint256 _index)
        public view returns (uint16)
    {
        StakerInfo storage info = stakerInfo[_staker];
        require(_index < info.subStakes.length);
        SubStakeInfo storage subStake = info.subStakes[_index];
        uint16 startPeriod = getStartPeriod(info, getCurrentPeriod());
        return getLastPeriodOfSubStake(subStake, startPeriod);
    }


    /**
    * @notice Get the value of locked tokens for a staker in a specified period
    * @dev Information may be incorrect for mined or unconfirmed surpassed period
    * @param _info Staker structure
    * @param _currentPeriod Current period
    * @param _period Next period
    **/
    function getLockedTokens(StakerInfo storage _info, uint16 _currentPeriod, uint16 _period)
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
    * @notice Get the value of locked tokens for a staker in a future period
    * @param _staker Staker
    * @param _periods Amount of periods that will be added to the current period
    **/
    function getLockedTokens(address _staker, uint16 _periods)
        public view returns (uint256 lockedValue)
    {
        StakerInfo storage info = stakerInfo[_staker];
        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod.add16(_periods);
        return getLockedTokens(info, currentPeriod, nextPeriod);
    }

    /**
    * @notice Get the value of locked tokens for a staker in a previous period
    * @dev Information may be incorrect for mined or unconfirmed surpassed period
    * @param _staker Staker
    * @param _periods Amount of periods that will be subtracted from the current period
    **/
    function getLockedTokensInPast(address _staker, uint16 _periods)
        public view returns (uint256 lockedValue)
    {
        StakerInfo storage info = stakerInfo[_staker];
        uint16 currentPeriod = getCurrentPeriod();
        uint16 previousPeriod = currentPeriod.sub16(_periods);
        return getLockedTokens(info, currentPeriod, previousPeriod);
    }

    /**
    * @notice Get the value of locked tokens for a staker in the current period
    * @param _staker Staker
    **/
    function getLockedTokens(address _staker)
        public view returns (uint256)
    {
        return getLockedTokens(_staker, 0);
    }

    /**
    * @notice Get the last active staker's period
    * @param _staker Staker
    **/
    function getLastActivePeriod(address _staker) public view returns (uint16) {
        StakerInfo storage info = stakerInfo[_staker];
        if (info.confirmedPeriod1 != EMPTY_CONFIRMED_PERIOD ||
            info.confirmedPeriod2 != EMPTY_CONFIRMED_PERIOD) {
            return AdditionalMath.max16(info.confirmedPeriod1, info.confirmedPeriod2);
        }
        return info.lastActivePeriod;
    }

    /**
    * @notice Get the value of locked tokens for active stakers in (getCurrentPeriod() + _periods) period
    * @param _periods Amount of periods for locked tokens calculation
    **/
    function getAllLockedTokens(uint16 _periods)
        external view returns (uint256 lockedTokens)
    {
        require(_periods > 0);
        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod.add16(_periods);
        for (uint256 i = 0; i < stakers.length; i++) {
            address staker = stakers[i];
            StakerInfo storage info = stakerInfo[staker];
            if (info.confirmedPeriod1 != currentPeriod &&
                info.confirmedPeriod2 != currentPeriod) {
                continue;
            }
            lockedTokens = lockedTokens.add(getLockedTokens(info, currentPeriod, nextPeriod));
        }
    }

    /**
    * @notice Checks if `reStake` parameter is available for changing
    * @param _staker Staker
    **/
    function isReStakeLocked(address _staker) public view returns (bool) {
        return getCurrentPeriod() < stakerInfo[_staker].lockReStakeUntilPeriod;
    }

    /**
    * @notice Get worker using staker's address
    **/
    function getWorkerFromStaker(address _staker) public view returns (address) {
        StakerInfo storage info = stakerInfo[_staker];
        // specified address is not a staker
        if (stakerInfo[_staker].subStakes.length == 0) {
            return address(0);
        }
        return info.worker;
    }

    /**
    * @notice Get staker using worker's address
    **/
    function getStakerFromWorker(address _worker) public view returns (address) {
        return workerToStaker[_worker];
    }

    /**
    * @notice Get work that completed by the staker
    **/
    function getCompletedWork(address _staker) public view returns (uint256) {
        return stakerInfo[_staker].completedWork;
    }

    //------------------------Main methods------------------------
    /**
    * @notice Start or stop measuring the work of a staker
    * @param _staker Staker
    * @param _measureWork Value for `measureWork` parameter
    * @return Work that was previously done
    **/
    function setWorkMeasurement(address _staker, bool _measureWork) public returns (uint256) {
        require(msg.sender == address(workLock));
        StakerInfo storage info = stakerInfo[_staker];
        info.measureWork = _measureWork;
        emit WorkMeasurementSet(_staker, _measureWork);
        return info.completedWork;
    }

    /** @notice Set worker
    * @param _worker Worker address. Must be a real address, not a contract
    **/
    function setWorker(address _worker) public onlyStaker {
        StakerInfo storage info = stakerInfo[msg.sender];
        require(_worker != info.worker, "Specified worker is already set for this staker");
        uint16 currentPeriod = getCurrentPeriod();
        if(info.worker != address(0)){ // If this staker had a worker ...
            // Check that enough time has passed to change it
            require(currentPeriod >= info.workerStartPeriod.add16(minWorkerPeriods),
                "Not enough time has passed since the previous setting worker");
            // Remove the old relation "worker->staker"
            workerToStaker[info.worker] = address(0);
        }

        if (_worker != address(0)){
            require(workerToStaker[_worker] == address(0), "Specified worker is already in use");
            require(stakerInfo[_worker].subStakes.length == 0 || _worker == msg.sender,
                "Specified worker is a staker");
            // Set new worker->staker relation
            workerToStaker[_worker] = msg.sender;
        }

        // Set new worker (or unset if _worker == address(0))
        info.worker = _worker;
        info.workerStartPeriod = currentPeriod;
        emit WorkerSet(msg.sender, _worker, currentPeriod);
    }

    /**
    * @notice Set `reStake` parameter. If true then all mining reward will be added to locked stake
    * Only if this parameter is not locked
    * @param _reStake Value for parameter
    **/
    function setReStake(bool _reStake) public isInitialized {
        require(!isReStakeLocked(msg.sender));
        StakerInfo storage info = stakerInfo[msg.sender];
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
        stakerInfo[msg.sender].lockReStakeUntilPeriod = _lockReStakeUntilPeriod;
        emit ReStakeLocked(msg.sender, _lockReStakeUntilPeriod);
    }

    /**
    * @notice Implementation of the receiveApproval(address,uint256,address,bytes) method
    * (see NuCypherToken contract). Deposit all tokens that were approved to transfer
    * @param _from Staker
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
        deposit(_from, _from, _value, uint16(payload));
    }

    /**
    * @notice Deposit tokens
    * @param _value Amount of tokens to deposit
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function deposit(uint256 _value, uint16 _periods) public {
        deposit(msg.sender, msg.sender, _value, _periods);
    }

    /**
    * @notice Deposit tokens
    * @param _staker Staker
    * @param _value Amount of tokens to deposit
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function deposit(address _staker, uint256 _value, uint16 _periods) public {
        deposit(_staker, msg.sender, _value, _periods);
    }

    /**
    * @notice Deposit tokens
    * @param _staker Staker
    * @param _payer Owner of tokens
    * @param _value Amount of tokens to deposit
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function deposit(address _staker, address _payer, uint256 _value, uint16 _periods) internal isInitialized {
        require(_value != 0);
        StakerInfo storage info = stakerInfo[_staker];
        require(workerToStaker[_staker] == address(0) || workerToStaker[_staker] == info.worker,
            "A staker can't be a worker for another staker");
        // initial stake of the staker
        if (info.subStakes.length == 0) {
            stakers.push(_staker);
            policyManager.register(_staker, getCurrentPeriod());
        }
        info.value = info.value.add(_value);
        token.safeTransferFrom(_payer, address(this), _value);
        lock(_staker, _value, _periods);
        emit Deposited(_staker, _value, _periods);
    }

    /**
    * @notice Lock some tokens as a stake
    * @param _value Amount of tokens which will be locked
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function lock(uint256 _value, uint16 _periods) public onlyStaker {
        lock(msg.sender, _value, _periods);
    }

    /**
    * @notice Lock some tokens as a stake
    * @param _staker Staker
    * @param _value Amount of tokens which will be locked
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function lock(address _staker, uint256 _value, uint16 _periods) internal {
        require(_value <= token.balanceOf(address(this)) &&
            _value >= minAllowableLockedTokens &&
            _periods >= minLockedPeriods);

        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod.add16(1);
        StakerInfo storage info = stakerInfo[_staker];
        uint256 lockedTokens = getLockedTokens(info, currentPeriod, nextPeriod);
        require(_value.add(lockedTokens) <= info.value &&
            _value.add(lockedTokens) <= maxAllowableLockedTokens);

        if (info.confirmedPeriod1 != nextPeriod && info.confirmedPeriod2 != nextPeriod) {
            saveSubStake(info, nextPeriod, 0, _periods, _value);
        } else {
            // next period is confirmed
            saveSubStake(info, nextPeriod, 0, _periods - 1, _value);
            lockedPerPeriod[nextPeriod] = lockedPerPeriod[nextPeriod].add(_value);
            emit ActivityConfirmed(_staker, nextPeriod, _value);
        }

        emit Locked(_staker, _value, nextPeriod, _periods);
    }

    /**
    * @notice Save sub stake. First tries to override inactive sub stake
    * @dev Inactive sub stake means that last period of sub stake has been surpassed and already mined
    * @param _info Staker structure
    * @param _firstPeriod First period of the sub stake
    * @param _lastPeriod Last period of the sub stake
    * @param _periods Duration of the sub stake in periods
    * @param _lockedValue Amount of locked tokens
    **/
    function saveSubStake(
        StakerInfo storage _info,
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
    function divideStake(uint256 _index, uint256 _newValue, uint16 _periods) public onlyStaker {
        StakerInfo storage info = stakerInfo[msg.sender];
        require(_newValue >= minAllowableLockedTokens &&
            _periods > 0 &&
            _index < info.subStakes.length);
        SubStakeInfo storage subStake = info.subStakes[_index];
        uint16 currentPeriod = getCurrentPeriod();
        uint16 startPeriod = getStartPeriod(info, currentPeriod);
        uint16 lastPeriod = getLastPeriodOfSubStake(subStake, startPeriod);
        require(lastPeriod > currentPeriod, "The sub stake must active at least in the next period");

        uint256 oldValue = subStake.lockedValue;
        subStake.lockedValue = oldValue.sub(_newValue);
        require(subStake.lockedValue >= minAllowableLockedTokens);
        saveSubStake(info, subStake.firstPeriod, 0, subStake.periods.add16(_periods), _newValue);
        emit Divided(msg.sender, oldValue, lastPeriod, _newValue, _periods);
        emit Locked(msg.sender, _newValue, subStake.firstPeriod, subStake.periods + _periods);
    }

    /**
    * @notice Prolong active sub stake
    * @param _index Index of the sub stake
    * @param _periods Amount of periods for extending sub stake
    **/
    function prolongStake(uint256 _index, uint16 _periods) public onlyStaker {
        StakerInfo storage info = stakerInfo[msg.sender];
        require(_periods > 0, "Incorrect parameters");
        SubStakeInfo storage subStake = info.subStakes[_index];
        uint16 currentPeriod = getCurrentPeriod();
        uint16 startPeriod = getStartPeriod(info, currentPeriod);
        uint16 lastPeriod = getLastPeriodOfSubStake(subStake, startPeriod);
        require(lastPeriod > currentPeriod, "The sub stake must active at least in the next period");

        subStake.periods = subStake.periods.add16(_periods);
        // if the sub stake ends in the next confirmed period then reset the `lastPeriod` field
        if (lastPeriod == startPeriod) {
            subStake.lastPeriod = 0;
        }
        require(lastPeriod.add16(_periods).sub16(currentPeriod) >= minLockedPeriods,
            "The extended sub stake must not be less than the minimum value");
        emit Locked(msg.sender, subStake.lockedValue, lastPeriod + 1, _periods);
    }

    /**
    * @notice Withdraw available amount of tokens to staker
    * @param _value Amount of tokens to withdraw
    **/
    function withdraw(uint256 _value) public onlyStaker {
        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod.add16(1);
        StakerInfo storage info = stakerInfo[msg.sender];
        // the max locked tokens in most cases will be in the current period
        // but when the staker locks more then we should use the next period
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
    function confirmActivity() external {
        address staker = getStakerFromWorker(msg.sender);
        require(stakerInfo[staker].value > 0, "Staker must have a stake to confirm activity");
        require(msg.sender == tx.origin, "Only worker with real address can confirm activity");

        uint16 lastActivePeriod = getLastActivePeriod(staker);
        mint(staker);
        StakerInfo storage info = stakerInfo[staker];
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

        // staker was inactive for several periods
        if (lastActivePeriod < currentPeriod) {
            info.pastDowntime.push(Downtime(lastActivePeriod + 1, currentPeriod));
        }
        emit ActivityConfirmed(staker, nextPeriod, lockedTokens);
    }

    /**
    * @notice Mint tokens for previous periods if staker locked their tokens and confirmed activity
    **/
    function mint() external onlyStaker {
        // save last active period to the storage if both periods will be empty after minting
        // because we won't be able to calculate last active period
        // see getLastActivePeriod(address)
        StakerInfo storage info = stakerInfo[msg.sender];
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
    * @notice Mint tokens for previous periods if staker locked their tokens and confirmed activity
    * @param _staker Staker
    **/
    function mint(address _staker) internal {
        uint16 currentPeriod = getCurrentPeriod();
        uint16 previousPeriod = currentPeriod.sub16(1);
        StakerInfo storage info = stakerInfo[_staker];

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
            reward = reward.add(mint(_staker, info, 1, currentPeriod, startPeriod));
        } else if (info.confirmedPeriod2 != EMPTY_CONFIRMED_PERIOD &&
            info.confirmedPeriod2 < info.confirmedPeriod1) {
            reward = reward.add(mint(_staker, info, 2, currentPeriod, startPeriod));
        }
        if (info.confirmedPeriod2 <= previousPeriod &&
            info.confirmedPeriod2 > info.confirmedPeriod1) {
            reward = reward.add(mint(_staker, info, 2, currentPeriod, startPeriod));
        } else if (info.confirmedPeriod1 <= previousPeriod &&
            info.confirmedPeriod1 > info.confirmedPeriod2) {
            reward = reward.add(mint(_staker, info, 1, currentPeriod, startPeriod));
        }

        info.value = info.value.add(reward);
        if (info.measureWork) {
            info.completedWork = info.completedWork.add(reward);
        }
        emit Mined(_staker, previousPeriod, reward);
    }

    /**
    * @notice Calculate reward for one period
    * @param _staker Staker's address
    * @param _info Staker structure
    * @param _confirmedPeriodNumber Number of confirmed period (1 or 2)
    * @param _currentPeriod Current period
    * @param _startPeriod Pre-calculated start period
    **/
    function mint(
        address _staker,
        StakerInfo storage _info,
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
        policyManager.updateReward(_staker, mintingPeriod);
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
    * @notice Get active stakers based on input points
    * @param _points Array of absolute values. Must be sorted in ascending order.
    * @param _periods Amount of periods for locked tokens calculation
    *
    * @dev This method implements the Probability Proportional to Size (PPS) sampling algorithm,
    * but with the random input data provided in the _points array.
    * In few words, the algorithm places in a line all active stakes that have locked tokens for
    * at least _periods periods; a staker is selected if an input point is within its stake.
    * For example:
    *
    * Stakes: |----- S0 ----|--------- S1 ---------|-- S2 --|---- S3 ---|-S4-|----- S5 -----|
    * Points: ....R0.......................R1..................R2...............R3...........
    *
    * In this case, Stakers 0, 1, 3 and 5 will be selected.
    *
    * Only stakers which confirmed the current period (in the previous period) are used.
    * If the number of points is more than the number of active stakers with suitable stakes,
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

        uint256 previousPoint = 0;
        uint256 pointIndex = 0;
        uint256 sumOfLockedTokens = 0;
        uint256 stakerIndex = 0;
        while (stakerIndex < stakers.length && pointIndex < _points.length) {
            address currentStaker = stakers[stakerIndex];
            StakerInfo storage info = stakerInfo[currentStaker];
            if (info.confirmedPeriod1 != currentPeriod &&
                info.confirmedPeriod2 != currentPeriod) {
                stakerIndex += 1;
                continue;
            }
            uint256 stakerTokens = getLockedTokens(info, currentPeriod, nextPeriod);
            uint256 nextSumValue = sumOfLockedTokens.add(stakerTokens);

            uint256 point = _points[pointIndex];
            require(point >= previousPoint);  // _points must be a sorted array
            if (sumOfLockedTokens <= point && point < nextSumValue) {
                result[pointIndex] = currentStaker;
                pointIndex += 1;
                previousPoint = point;
            } else {
                stakerIndex += 1;
                sumOfLockedTokens = nextSumValue;
            }
        }
    }

    //-------------------------Slashing-------------------------
    /**
    * @notice Slash the staker's stake and reward the investigator
    * @param _staker Staker's address
    * @param _penalty Penalty
    * @param _investigator Investigator
    * @param _reward Reward for the investigator
    **/
    function slashStaker(
        address _staker,
        uint256 _penalty,
        address _investigator,
        uint256 _reward
    )
        public
    {
        require(msg.sender == address(adjudicator));
        require(_penalty > 0);
        StakerInfo storage info = stakerInfo[_staker];
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

        // Decrease the stake if amount of locked tokens in the current period more than staker has
        uint256 lockedTokens = currentLock + currentAndNextLock;
        if (info.value < lockedTokens) {
           decreaseSubStakes(info, lockedTokens - info.value, currentPeriod, startPeriod, shortestSubStakeIndex);
        }
        // Decrease the stake if amount of locked tokens in the next period more than staker has
        if (nextLock > 0) {
            lockedTokens = nextLock + currentAndNextLock -
                (currentAndNextLock > info.value ? currentAndNextLock - info.value : 0);
            if (info.value < lockedTokens) {
               decreaseSubStakes(info, lockedTokens - info.value, nextPeriod, startPeriod, MAX_SUB_STAKES);
            }
        }

        emit Slashed(_staker, _penalty, _investigator, _reward);
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
    * @notice Get the value of locked tokens for a staker in the current and the next period
    * and find the shortest sub stake
    * @param _info Staker structure
    * @param _currentPeriod Current period
    * @param _nextPeriod Next period
    * @param _startPeriod Pre-calculated start period
    * @return currentLock Amount of tokens that locked in the current period and unlocked in the next period
    * @return nextLock Amount of tokens that locked in the next period and not locked in the current period
    * @return currentAndNextLock Amount of tokens that locked in the current period and in the next period
    * @return shortestSubStakeIndex Index of the shortest sub stake
    **/
    function getLockedTokensAndShortestSubStake(
        StakerInfo storage _info,
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
    * @param _info Staker structure
    * @param _penalty Penalty rate
    * @param _decreasePeriod The period when the decrease begins
    * @param _startPeriod Pre-calculated start period
    * @param _shortestSubStakeIndex Index of the shortest period
    **/
    function decreaseSubStakes(
        StakerInfo storage _info,
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
    * @param _info Staker structure
    * @param _currentPeriod Current period
    * @param _startPeriod Pre-calculated start period
    * @return shortestSubStake The shortest sub stake
    * @return minSubStakeDuration Duration of the shortest sub stake
    * @return minSubStakeLastPeriod Last period of the shortest sub stake
    **/
    function getShortestSubStake(
        StakerInfo storage _info,
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
    * @param _info Staker structure
    * @param _firstPeriod First period of the old sub stake
    * @param _lockedValue Locked value of the old sub stake
    * @param _currentPeriod Current period, when the old sub stake is already unlocked
    **/
    function saveOldSubStake(
        StakerInfo storage _info,
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

    //-------------Additional getters for stakers info-------------
    /**
    * @notice Return the length of the array of stakers
    **/
    function getStakersLength() public view returns (uint256) {
        return stakers.length;
    }

    /**
    * @notice Return the length of the array of sub stakes
    **/
    function getSubStakesLength(address _staker) public view returns (uint256) {
        return stakerInfo[_staker].subStakes.length;
    }

    /**
    * @notice Return the information about sub stake
    **/
    function getSubStakeInfo(address _staker, uint256 _index)
    // TODO change to structure when ABIEncoderV2 is released
//        public view returns (SubStakeInfo)
        public view returns (uint16 firstPeriod, uint16 lastPeriod, uint16 periods, uint256 lockedValue)
    {
        SubStakeInfo storage info = stakerInfo[_staker].subStakes[_index];
        firstPeriod = info.firstPeriod;
        lastPeriod = info.lastPeriod;
        periods = info.periods;
        lockedValue = info.lockedValue;
    }

    /**
    * @notice Return the length of the array of past downtime
    **/
    function getPastDowntimeLength(address _staker) public view returns (uint256) {
        return stakerInfo[_staker].pastDowntime.length;
    }

    /**
    * @notice Return the information about past downtime
    **/
    function  getPastDowntime(address _staker, uint256 _index)
    // TODO change to structure when ABIEncoderV2 is released
//        public view returns (Downtime)
        public view returns (uint16 startPeriod, uint16 endPeriod)
    {
        Downtime storage downtime = stakerInfo[_staker].pastDowntime[_index];
        startPeriod = downtime.startPeriod;
        endPeriod = downtime.endPeriod;
    }


    //------------------------Upgradeable------------------------
    /**
    * @dev Get StakerInfo structure by delegatecall
    **/
    function delegateGetStakerInfo(address _target, bytes32 _staker)
        internal returns (StakerInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, "stakerInfo(address)", 1, _staker, 0);
        assembly {
            result := memoryAddress
            // copy data to the right position after the array pointer place
            // measureWork
            mstore(add(memoryAddress, 0x140), mload(add(memoryAddress, 0x100)))
            // completedWork
            mstore(add(memoryAddress, 0x160), mload(add(memoryAddress, 0x120)))
        }
    }

    /**
    * @dev Get SubStakeInfo structure by delegatecall
    **/
    function delegateGetSubStakeInfo(address _target, bytes32 _staker, uint256 _index)
        internal returns (SubStakeInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(
            _target, "getSubStakeInfo(address,uint256)", 2, _staker, bytes32(_index));
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get Downtime structure by delegatecall
    **/
    function delegateGetPastDowntime(address _target, bytes32 _staker, uint256 _index)
        internal returns (Downtime memory result)
    {
        bytes32 memoryAddress = delegateGetData(
            _target, "getPastDowntime(address,uint256)", 2, _staker, bytes32(_index));
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
        require(address(delegateGet(_testTarget, "adjudicator()")) == address(adjudicator));
        require(address(delegateGet(_testTarget, "workLock()")) == address(workLock));
        require(delegateGet(_testTarget, "lockedPerPeriod(uint16)",
            bytes32(bytes2(RESERVED_PERIOD))) == lockedPerPeriod[RESERVED_PERIOD]);
        require(address(delegateGet(_testTarget, "workerToStaker(address)", bytes32(0))) ==
            workerToStaker[address(0)]);

        require(delegateGet(_testTarget, "getStakersLength()") == stakers.length);
        if (stakers.length == 0) {
            return;
        }
        address stakerAddress = stakers[0];
        require(address(uint160(delegateGet(_testTarget, "stakers(uint256)", 0))) == stakerAddress);
        StakerInfo storage info = stakerInfo[stakerAddress];
        bytes32 staker = bytes32(uint256(stakerAddress));
        StakerInfo memory infoToCheck = delegateGetStakerInfo(_testTarget, staker);
        require(infoToCheck.value == info.value &&
            infoToCheck.confirmedPeriod1 == info.confirmedPeriod1 &&
            infoToCheck.confirmedPeriod2 == info.confirmedPeriod2 &&
            infoToCheck.reStake == info.reStake &&
            infoToCheck.lockReStakeUntilPeriod == info.lockReStakeUntilPeriod &&
            infoToCheck.lastActivePeriod == info.lastActivePeriod &&
            infoToCheck.measureWork == info.measureWork &&
            infoToCheck.completedWork == info.completedWork &&
            infoToCheck.worker == info.worker &&
            infoToCheck.workerStartPeriod == info.workerStartPeriod);

        require(delegateGet(_testTarget, "getPastDowntimeLength(address)", staker) ==
            info.pastDowntime.length);
        for (uint256 i = 0; i < info.pastDowntime.length && i < MAX_CHECKED_VALUES; i++) {
            Downtime storage downtime = info.pastDowntime[i];
            Downtime memory downtimeToCheck = delegateGetPastDowntime(_testTarget, staker, i);
            require(downtimeToCheck.startPeriod == downtime.startPeriod &&
                downtimeToCheck.endPeriod == downtime.endPeriod);
        }

        require(delegateGet(_testTarget, "getSubStakesLength(address)", staker) == info.subStakes.length);
        for (uint256 i = 0; i < info.subStakes.length && i < MAX_CHECKED_VALUES; i++) {
            SubStakeInfo storage subStakeInfo = info.subStakes[i];
            SubStakeInfo memory subStakeInfoToCheck = delegateGetSubStakeInfo(_testTarget, staker, i);
            require(subStakeInfoToCheck.firstPeriod == subStakeInfo.firstPeriod &&
                subStakeInfoToCheck.lastPeriod == subStakeInfo.lastPeriod &&
                subStakeInfoToCheck.periods == subStakeInfo.periods &&
                subStakeInfoToCheck.lockedValue == subStakeInfo.lockedValue);
        }

        if (info.worker != address(0)) {
            require(address(delegateGet(_testTarget, "workerToStaker(address)", bytes32(uint256(info.worker)))) ==
                workerToStaker[info.worker]);
        }
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `finishUpgrade`
    function finishUpgrade(address _target) public {
        super.finishUpgrade(_target);
        StakingEscrow escrow = StakingEscrow(_target);
        minLockedPeriods = escrow.minLockedPeriods();
        minAllowableLockedTokens = escrow.minAllowableLockedTokens();
        maxAllowableLockedTokens = escrow.maxAllowableLockedTokens();
        minWorkerPeriods = escrow.minWorkerPeriods();

        // Create fake period
        lockedPerPeriod[RESERVED_PERIOD] = 111;

        // Create fake worker
        workerToStaker[address(0)] = address(this);
    }
}
