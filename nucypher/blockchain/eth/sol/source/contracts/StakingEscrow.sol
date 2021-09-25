// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


import "aragon/interfaces/IERC900History.sol";
import "contracts/Issuer.sol";
import "contracts/lib/Bits.sol";
import "contracts/lib/Snapshot.sol";
import "zeppelin/math/SafeMath.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";


/**
* @notice PolicyManager interface
*/
interface PolicyManagerInterface {
    function secondsPerPeriod() external view returns (uint32);
    function register(address _node, uint16 _period) external;
    function migrate(address _node) external;
    function ping(
        address _node,
        uint16 _processedPeriod1,
        uint16 _processedPeriod2,
        uint16 _periodToSetDefault
    ) external;
}


/**
* @notice Adjudicator interface
*/
interface AdjudicatorInterface {
    function rewardCoefficient() external view returns (uint32);
}


/**
* @notice WorkLock interface
*/
interface WorkLockInterface {
    function token() external view returns (NuCypherToken);
}

/**
* @title StakingEscrowStub
* @notice Stub is used to deploy main StakingEscrow after all other contract and make some variables immutable
* @dev |v1.0.1|
*/
contract StakingEscrowStub is Upgradeable {
    using AdditionalMath for uint32;

    NuCypherToken public immutable token;
    uint32 public immutable genesisSecondsPerPeriod;
    uint32 public immutable secondsPerPeriod;
    uint16 public immutable minLockedPeriods;
    uint256 public immutable minAllowableLockedTokens;
    uint256 public immutable maxAllowableLockedTokens;

    /**
    * @notice Predefines some variables for use when deploying other contracts
    * @param _token Token contract
    * @param _genesisHoursPerPeriod Size of period in hours at genesis
    * @param _hoursPerPeriod Size of period in hours
    * @param _minLockedPeriods Min amount of periods during which tokens can be locked
    * @param _minAllowableLockedTokens Min amount of tokens that can be locked
    * @param _maxAllowableLockedTokens Max amount of tokens that can be locked
    */
    constructor(
        NuCypherToken _token,
        uint32 _genesisHoursPerPeriod,
        uint32 _hoursPerPeriod,
        uint16 _minLockedPeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens
    ) {
        require(_token.totalSupply() > 0 &&
            _hoursPerPeriod != 0 &&
            _genesisHoursPerPeriod != 0 &&
            _genesisHoursPerPeriod <= _hoursPerPeriod &&
            _minLockedPeriods > 1 &&
            _maxAllowableLockedTokens != 0);

        token = _token;
        secondsPerPeriod = _hoursPerPeriod.mul32(1 hours);
        genesisSecondsPerPeriod = _genesisHoursPerPeriod.mul32(1 hours);
        minLockedPeriods = _minLockedPeriods;
        minAllowableLockedTokens = _minAllowableLockedTokens;
        maxAllowableLockedTokens = _maxAllowableLockedTokens;
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `verifyState`
    function verifyState(address _testTarget) public override virtual {
        super.verifyState(_testTarget);

        // we have to use real values even though this is a stub
        require(address(delegateGet(_testTarget, this.token.selector)) == address(token));
        require(uint32(delegateGet(_testTarget, this.genesisSecondsPerPeriod.selector)) == genesisSecondsPerPeriod);
        require(uint32(delegateGet(_testTarget, this.secondsPerPeriod.selector)) == secondsPerPeriod);
        require(uint16(delegateGet(_testTarget, this.minLockedPeriods.selector)) == minLockedPeriods);
        require(delegateGet(_testTarget, this.minAllowableLockedTokens.selector) == minAllowableLockedTokens);
        require(delegateGet(_testTarget, this.maxAllowableLockedTokens.selector) == maxAllowableLockedTokens);
    }
}


/**
* @title StakingEscrow
* @notice Contract holds and locks stakers tokens.
* Each staker that locks their tokens will receive some compensation
* @dev |v5.7.2|
*/
contract StakingEscrow is Issuer, IERC900History {

    using AdditionalMath for uint256;
    using AdditionalMath for uint16;
    using Bits for uint256;
    using SafeMath for uint256;
    using Snapshot for uint128[];
    using SafeERC20 for NuCypherToken;

    /**
    * @notice Signals that tokens were deposited
    * @param staker Staker address
    * @param value Amount deposited (in NuNits)
    * @param periods Number of periods tokens will be locked
    */
    event Deposited(address indexed staker, uint256 value, uint16 periods);

    /**
    * @notice Signals that tokens were stake locked
    * @param staker Staker address
    * @param value Amount locked (in NuNits)
    * @param firstPeriod Starting lock period
    * @param periods Number of periods tokens will be locked
    */
    event Locked(address indexed staker, uint256 value, uint16 firstPeriod, uint16 periods);

    /**
    * @notice Signals that a sub-stake was divided
    * @param staker Staker address
    * @param oldValue Old sub-stake value (in NuNits)
    * @param lastPeriod Final locked period of old sub-stake
    * @param newValue New sub-stake value (in NuNits)
    * @param periods Number of periods to extend sub-stake
    */
    event Divided(
        address indexed staker,
        uint256 oldValue,
        uint16 lastPeriod,
        uint256 newValue,
        uint16 periods
    );

    /**
    * @notice Signals that two sub-stakes were merged
    * @param staker Staker address
    * @param value1 Value of first sub-stake (in NuNits)
    * @param value2 Value of second sub-stake (in NuNits)
    * @param lastPeriod Final locked period of merged sub-stake
    */
    event Merged(address indexed staker, uint256 value1, uint256 value2, uint16 lastPeriod);

    /**
    * @notice Signals that a sub-stake was prolonged
    * @param staker Staker address
    * @param value Value of sub-stake
    * @param lastPeriod Final locked period of old sub-stake
    * @param periods Number of periods sub-stake was extended
    */
    event Prolonged(address indexed staker, uint256 value, uint16 lastPeriod, uint16 periods);

    /**
    * @notice Signals that tokens were withdrawn to the staker
    * @param staker Staker address
    * @param value Amount withdraws (in NuNits)
    */
    event Withdrawn(address indexed staker, uint256 value);

    /**
    * @notice Signals that the worker associated with the staker made a commitment to next period
    * @param staker Staker address
    * @param period Period committed to
    * @param value Amount of tokens staked for the committed period
    */
    event CommitmentMade(address indexed staker, uint16 indexed period, uint256 value);

    /**
    * @notice Signals that tokens were minted for previous periods
    * @param staker Staker address
    * @param period Previous period tokens minted for
    * @param value Amount minted (in NuNits)
    */
    event Minted(address indexed staker, uint16 indexed period, uint256 value);

    /**
    * @notice Signals that the staker was slashed
    * @param staker Staker address
    * @param penalty Slashing penalty
    * @param investigator Investigator address
    * @param reward Value of reward provided to investigator (in NuNits)
    */
    event Slashed(address indexed staker, uint256 penalty, address indexed investigator, uint256 reward);

    /**
    * @notice Signals that the restake parameter was activated/deactivated
    * @param staker Staker address
    * @param reStake Updated parameter value
    */
    event ReStakeSet(address indexed staker, bool reStake);

    /**
    * @notice Signals that a worker was bonded to the staker
    * @param staker Staker address
    * @param worker Worker address
    * @param startPeriod Period bonding occurred
    */
    event WorkerBonded(address indexed staker, address indexed worker, uint16 indexed startPeriod);

    /**
    * @notice Signals that the winddown parameter was activated/deactivated
    * @param staker Staker address
    * @param windDown Updated parameter value
    */
    event WindDownSet(address indexed staker, bool windDown);

    /**
    * @notice Signals that the snapshot parameter was activated/deactivated
    * @param staker Staker address
    * @param snapshotsEnabled Updated parameter value
    */
    event SnapshotSet(address indexed staker, bool snapshotsEnabled);

    /**
    * @notice Signals that the staker migrated their stake to the new period length
    * @param staker Staker address
    * @param period Period when migration happened
    */
    event Migrated(address indexed staker, uint16 indexed period);

    /// internal event
    event WorkMeasurementSet(address indexed staker, bool measureWork);

    struct SubStakeInfo {
        uint16 firstPeriod;
        uint16 lastPeriod;
        uint16 unlockingDuration;
        uint128 lockedValue;
    }

    struct Downtime {
        uint16 startPeriod;
        uint16 endPeriod;
    }

    struct StakerInfo {
        uint256 value;
        /*
        * Stores periods that are committed but not yet rewarded.
        * In order to optimize storage, only two values are used instead of an array.
        * commitToNextPeriod() method invokes mint() method so there can only be two committed
        * periods that are not yet rewarded: the current and the next periods.
        */
        uint16 currentCommittedPeriod;
        uint16 nextCommittedPeriod;
        uint16 lastCommittedPeriod;
        uint16 stub1; // former slot for lockReStakeUntilPeriod
        uint256 completedWork;
        uint16 workerStartPeriod; // period when worker was bonded
        address worker;
        uint256 flags; // uint256 to acquire whole slot and minimize operations on it

        uint256 reservedSlot1;
        uint256 reservedSlot2;
        uint256 reservedSlot3;
        uint256 reservedSlot4;
        uint256 reservedSlot5;

        Downtime[] pastDowntime;
        SubStakeInfo[] subStakes;
        uint128[] history;

    }

    // used only for upgrading
    uint16 internal constant RESERVED_PERIOD = 0;
    uint16 internal constant MAX_CHECKED_VALUES = 5;
    // to prevent high gas consumption in loops for slashing
    uint16 public constant MAX_SUB_STAKES = 30;
    uint16 internal constant MAX_UINT16 = 65535;

    // indices for flags
    uint8 internal constant RE_STAKE_DISABLED_INDEX = 0;
    uint8 internal constant WIND_DOWN_INDEX = 1;
    uint8 internal constant MEASURE_WORK_INDEX = 2;
    uint8 internal constant SNAPSHOTS_DISABLED_INDEX = 3;
    uint8 internal constant MIGRATED_INDEX = 4;

    uint16 public immutable minLockedPeriods;
    uint16 public immutable minWorkerPeriods;
    uint256 public immutable minAllowableLockedTokens;
    uint256 public immutable maxAllowableLockedTokens;

    PolicyManagerInterface public immutable policyManager;
    AdjudicatorInterface public immutable adjudicator;
    WorkLockInterface public immutable workLock;

    mapping (address => StakerInfo) public stakerInfo;
    address[] public stakers;
    mapping (address => address) public stakerFromWorker;

    mapping (uint16 => uint256) stub4; // former slot for lockedPerPeriod
    uint128[] public balanceHistory;

    address stub1; // former slot for PolicyManager
    address stub2; // former slot for Adjudicator
    address stub3; // former slot for WorkLock

    mapping (uint16 => uint256) public lockedPerPeriod;

    /**
    * @notice Constructor sets address of token contract and coefficients for minting
    * @param _token Token contract
    * @param _policyManager Policy Manager contract
    * @param _adjudicator Adjudicator contract
    * @param _workLock WorkLock contract. Zero address if there is no WorkLock
    * @param _genesisHoursPerPeriod Size of period in hours at genesis
    * @param _hoursPerPeriod Size of period in hours
    * @param _issuanceDecayCoefficient (d) Coefficient which modifies the rate at which the maximum issuance decays,
    * only applicable to Phase 2. d = 365 * half-life / LOG2 where default half-life = 2.
    * See Equation 10 in Staking Protocol & Economics paper
    * @param _lockDurationCoefficient1 (k1) Numerator of the coefficient which modifies the extent
    * to which a stake's lock duration affects the subsidy it receives. Affects stakers differently.
    * Applicable to Phase 1 and Phase 2. k1 = k2 * small_stake_multiplier where default small_stake_multiplier = 0.5.
    * See Equation 8 in Staking Protocol & Economics paper.
    * @param _lockDurationCoefficient2 (k2) Denominator of the coefficient which modifies the extent
    * to which a stake's lock duration affects the subsidy it receives. Affects stakers differently.
    * Applicable to Phase 1 and Phase 2. k2 = maximum_rewarded_periods / (1 - small_stake_multiplier)
    * where default maximum_rewarded_periods = 365 and default small_stake_multiplier = 0.5.
    * See Equation 8 in Staking Protocol & Economics paper.
    * @param _maximumRewardedPeriods (kmax) Number of periods beyond which a stake's lock duration
    * no longer increases the subsidy it receives. kmax = reward_saturation * 365 where default reward_saturation = 1.
    * See Equation 8 in Staking Protocol & Economics paper.
    * @param _firstPhaseTotalSupply Total supply for the first phase
    * @param _firstPhaseMaxIssuance (Imax) Maximum number of new tokens minted per period during Phase 1.
    * See Equation 7 in Staking Protocol & Economics paper.
    * @param _minLockedPeriods Min amount of periods during which tokens can be locked
    * @param _minAllowableLockedTokens Min amount of tokens that can be locked
    * @param _maxAllowableLockedTokens Max amount of tokens that can be locked
    * @param _minWorkerPeriods Min amount of periods while a worker can't be changed
    */
    constructor(
        NuCypherToken _token,
        PolicyManagerInterface _policyManager,
        AdjudicatorInterface _adjudicator,
        WorkLockInterface _workLock,
        uint32 _genesisHoursPerPeriod,
        uint32 _hoursPerPeriod,
        uint256 _issuanceDecayCoefficient,
        uint256 _lockDurationCoefficient1,
        uint256 _lockDurationCoefficient2,
        uint16 _maximumRewardedPeriods,
        uint256 _firstPhaseTotalSupply,
        uint256 _firstPhaseMaxIssuance,
        uint16 _minLockedPeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens,
        uint16 _minWorkerPeriods
    )
        Issuer(
            _token,
            _genesisHoursPerPeriod,
            _hoursPerPeriod,
            _issuanceDecayCoefficient,
            _lockDurationCoefficient1,
            _lockDurationCoefficient2,
            _maximumRewardedPeriods,
            _firstPhaseTotalSupply,
            _firstPhaseMaxIssuance
        )
    {
        // constant `1` in the expression `_minLockedPeriods > 1` uses to simplify the `lock` method
        require(_minLockedPeriods > 1 && _maxAllowableLockedTokens != 0);
        minLockedPeriods = _minLockedPeriods;
        minAllowableLockedTokens = _minAllowableLockedTokens;
        maxAllowableLockedTokens = _maxAllowableLockedTokens;
        minWorkerPeriods = _minWorkerPeriods;

        require((_policyManager.secondsPerPeriod() == _hoursPerPeriod * (1 hours) ||
            _policyManager.secondsPerPeriod() == _genesisHoursPerPeriod * (1 hours)) &&
            _adjudicator.rewardCoefficient() != 0 &&
            (address(_workLock) == address(0) || _workLock.token() == _token));
        policyManager = _policyManager;
        adjudicator = _adjudicator;
        workLock = _workLock;
    }

    /**
    * @dev Checks the existence of a staker in the contract
    */
    modifier onlyStaker()
    {
        StakerInfo storage info = stakerInfo[msg.sender];
        require((info.value > 0 || info.nextCommittedPeriod != 0) &&
            info.flags.bitSet(MIGRATED_INDEX));
        _;
    }

    //------------------------Main getters------------------------
    /**
    * @notice Get all tokens belonging to the staker
    */
    function getAllTokens(address _staker) external view returns (uint256) {
        return stakerInfo[_staker].value;
    }

    /**
    * @notice Get all flags for the staker
    */
    function getFlags(address _staker)
        external view returns (
            bool windDown,
            bool reStake,
            bool measureWork,
            bool snapshots,
            bool migrated
        )
    {
        StakerInfo storage info = stakerInfo[_staker];
        windDown = info.flags.bitSet(WIND_DOWN_INDEX);
        reStake = !info.flags.bitSet(RE_STAKE_DISABLED_INDEX);
        measureWork = info.flags.bitSet(MEASURE_WORK_INDEX);
        snapshots = !info.flags.bitSet(SNAPSHOTS_DISABLED_INDEX);
        migrated = info.flags.bitSet(MIGRATED_INDEX);
    }

    /**
    * @notice Get the start period. Use in the calculation of the last period of the sub stake
    * @param _info Staker structure
    * @param _currentPeriod Current period
    */
    function getStartPeriod(StakerInfo storage _info, uint16 _currentPeriod)
        internal view returns (uint16)
    {
        // if the next period (after current) is committed
        if (_info.flags.bitSet(WIND_DOWN_INDEX) && _info.nextCommittedPeriod > _currentPeriod) {
            return _currentPeriod + 1;
        }
        return _currentPeriod;
    }

    /**
    * @notice Get the last period of the sub stake
    * @param _subStake Sub stake structure
    * @param _startPeriod Pre-calculated start period
    */
    function getLastPeriodOfSubStake(SubStakeInfo storage _subStake, uint16 _startPeriod)
        internal view returns (uint16)
    {
        if (_subStake.lastPeriod != 0) {
            return _subStake.lastPeriod;
        }
        uint32 lastPeriod = uint32(_startPeriod) + _subStake.unlockingDuration;
        if (lastPeriod > uint32(MAX_UINT16)) {
            return MAX_UINT16;
        }
        return uint16(lastPeriod);
    }

    /**
    * @notice Get the last period of the sub stake
    * @param _staker Staker
    * @param _index Stake index
    */
    function getLastPeriodOfSubStake(address _staker, uint256 _index)
        public view returns (uint16)
    {
        StakerInfo storage info = stakerInfo[_staker];
        SubStakeInfo storage subStake = info.subStakes[_index];
        uint16 startPeriod = getStartPeriod(info, getCurrentPeriod());
        return getLastPeriodOfSubStake(subStake, startPeriod);
    }


    /**
    * @notice Get the value of locked tokens for a staker in a specified period
    * @dev Information may be incorrect for rewarded or not committed surpassed period
    * @param _info Staker structure
    * @param _currentPeriod Current period
    * @param _period Next period
    */
    function getLockedTokens(StakerInfo storage _info, uint16 _currentPeriod, uint16 _period)
        internal view returns (uint256 lockedValue)
    {
        lockedValue = 0;
        uint16 startPeriod = getStartPeriod(_info, _currentPeriod);
        for (uint256 i = 0; i < _info.subStakes.length; i++) {
            SubStakeInfo storage subStake = _info.subStakes[i];
            if (subStake.firstPeriod <= _period &&
                getLastPeriodOfSubStake(subStake, startPeriod) >= _period) {
                lockedValue += subStake.lockedValue;
            }
        }
    }

    /**
    * @notice Get the value of locked tokens for a staker in a future period
    * @dev This function is used by PreallocationEscrow so its signature can't be updated.
    * @param _staker Staker
    * @param _offsetPeriods Amount of periods that will be added to the current period
    */
    function getLockedTokens(address _staker, uint16 _offsetPeriods)
        external view returns (uint256 lockedValue)
    {
        StakerInfo storage info = stakerInfo[_staker];
        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod.add16(_offsetPeriods);
        return getLockedTokens(info, currentPeriod, nextPeriod);
    }

    /**
    * @notice Get the last committed staker's period
    * @param _staker Staker
    */
    function getLastCommittedPeriod(address _staker) public view returns (uint16) {
        StakerInfo storage info = stakerInfo[_staker];
        return info.nextCommittedPeriod != 0 ? info.nextCommittedPeriod : info.lastCommittedPeriod;
    }

    /**
    * @notice Get the value of locked tokens for active stakers in (getCurrentPeriod() + _offsetPeriods) period
    * as well as stakers and their locked tokens
    * @param _offsetPeriods Amount of periods for locked tokens calculation
    * @param _startIndex Start index for looking in stakers array
    * @param _maxStakers Max stakers for looking, if set 0 then all will be used
    * @return allLockedTokens Sum of locked tokens for active stakers
    * @return activeStakers Array of stakers and their locked tokens. Stakers addresses stored as uint256
    * @dev Note that activeStakers[0] in an array of uint256, but you want addresses. Careful when used directly!
    */
    function getActiveStakers(uint16 _offsetPeriods, uint256 _startIndex, uint256 _maxStakers)
        external view returns (uint256 allLockedTokens, uint256[2][] memory activeStakers)
    {
        require(_offsetPeriods > 0);

        uint256 endIndex = stakers.length;
        require(_startIndex < endIndex);
        if (_maxStakers != 0 && _startIndex + _maxStakers < endIndex) {
            endIndex = _startIndex + _maxStakers;
        }
        activeStakers = new uint256[2][](endIndex - _startIndex);
        allLockedTokens = 0;

        uint256 resultIndex = 0;
        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod.add16(_offsetPeriods);

        for (uint256 i = _startIndex; i < endIndex; i++) {
            address staker = stakers[i];
            StakerInfo storage info = stakerInfo[staker];
            if (info.currentCommittedPeriod != currentPeriod &&
                info.nextCommittedPeriod != currentPeriod) {
                continue;
            }
            uint256 lockedTokens = getLockedTokens(info, currentPeriod, nextPeriod);
            if (lockedTokens != 0) {
                activeStakers[resultIndex][0] = uint256(staker);
                activeStakers[resultIndex++][1] = lockedTokens;
                allLockedTokens += lockedTokens;
            }
        }
        assembly {
            mstore(activeStakers, resultIndex)
        }
    }

    /**
    * @notice Get worker using staker's address
    */
    function getWorkerFromStaker(address _staker) external view returns (address) {
        return stakerInfo[_staker].worker;
    }

    /**
    * @notice Get work that completed by the staker
    */
    function getCompletedWork(address _staker) external view returns (uint256) {
        return stakerInfo[_staker].completedWork;
    }

    /**
    * @notice Find index of downtime structure that includes specified period
    * @dev If specified period is outside all downtime periods, the length of the array will be returned
    * @param _staker Staker
    * @param _period Specified period number
    */
    function findIndexOfPastDowntime(address _staker, uint16 _period) external view returns (uint256 index) {
        StakerInfo storage info = stakerInfo[_staker];
        for (index = 0; index < info.pastDowntime.length; index++) {
            if (_period <= info.pastDowntime[index].endPeriod) {
                return index;
            }
        }
    }

    //------------------------Main methods------------------------
    /**
    * @notice Start or stop measuring the work of a staker
    * @param _staker Staker
    * @param _measureWork Value for `measureWork` parameter
    * @return Work that was previously done
    */
    function setWorkMeasurement(address _staker, bool _measureWork) external returns (uint256) {
        require(msg.sender == address(workLock));
        StakerInfo storage info = stakerInfo[_staker];
        if (info.flags.bitSet(MEASURE_WORK_INDEX) == _measureWork) {
            return info.completedWork;
        }
        info.flags = info.flags.toggleBit(MEASURE_WORK_INDEX);
        emit WorkMeasurementSet(_staker, _measureWork);
        return info.completedWork;
    }

    /**
    * @notice Bond worker
    * @param _worker Worker address. Must be a real address, not a contract
    */
    function bondWorker(address _worker) external onlyStaker {
        StakerInfo storage info = stakerInfo[msg.sender];
        // Specified worker is already bonded with this staker
        require(_worker != info.worker);
        uint16 currentPeriod = getCurrentPeriod();
        if (info.worker != address(0)) { // If this staker had a worker ...
            // Check that enough time has passed to change it
            require(currentPeriod >= info.workerStartPeriod.add16(minWorkerPeriods));
            // Remove the old relation "worker->staker"
            stakerFromWorker[info.worker] = address(0);
        }

        if (_worker != address(0)) {
            // Specified worker is already in use
            require(stakerFromWorker[_worker] == address(0));
            // Specified worker is a staker
            require(stakerInfo[_worker].subStakes.length == 0 || _worker == msg.sender);
            // Set new worker->staker relation
            stakerFromWorker[_worker] = msg.sender;
        }

        // Bond new worker (or unbond if _worker == address(0))
        info.worker = _worker;
        info.workerStartPeriod = currentPeriod;
        emit WorkerBonded(msg.sender, _worker, currentPeriod);
    }

    /**
    * @notice Set `reStake` parameter. If true then all staking rewards will be added to locked stake
    * @param _reStake Value for parameter
    */
    function setReStake(bool _reStake) external {
        StakerInfo storage info = stakerInfo[msg.sender];
        if (info.flags.bitSet(RE_STAKE_DISABLED_INDEX) == !_reStake) {
            return;
        }
        info.flags = info.flags.toggleBit(RE_STAKE_DISABLED_INDEX);
        emit ReStakeSet(msg.sender, _reStake);
    }

    /**
    * @notice Deposit tokens from WorkLock contract
    * @param _staker Staker address
    * @param _value Amount of tokens to deposit
    * @param _unlockingDuration Amount of periods during which tokens will be unlocked when wind down is enabled
    */
    function depositFromWorkLock(
        address _staker,
        uint256 _value,
        uint16 _unlockingDuration
    )
        external
    {
        require(msg.sender == address(workLock));
        StakerInfo storage info = stakerInfo[_staker];
        if (!info.flags.bitSet(WIND_DOWN_INDEX) && info.subStakes.length == 0) {
            info.flags = info.flags.toggleBit(WIND_DOWN_INDEX);
            emit WindDownSet(_staker, true);
        }
        // WorkLock still uses the genesis period length (24h)
        _unlockingDuration = recalculatePeriod(_unlockingDuration);
        deposit(_staker, msg.sender, MAX_SUB_STAKES, _value, _unlockingDuration);
    }

    /**
    * @notice Set `windDown` parameter.
    * If true then stake's duration will be decreasing in each period with `commitToNextPeriod()`
    * @param _windDown Value for parameter
    */
    function setWindDown(bool _windDown) external {
        StakerInfo storage info = stakerInfo[msg.sender];
        if (info.flags.bitSet(WIND_DOWN_INDEX) == _windDown) {
            return;
        }
        info.flags = info.flags.toggleBit(WIND_DOWN_INDEX);
        emit WindDownSet(msg.sender, _windDown);

        // duration adjustment if next period is committed
        uint16 nextPeriod = getCurrentPeriod() + 1;
        if (info.nextCommittedPeriod != nextPeriod) {
           return;
        }

        // adjust sub-stakes duration for the new value of winding down parameter
        for (uint256 index = 0; index < info.subStakes.length; index++) {
            SubStakeInfo storage subStake = info.subStakes[index];
            // sub-stake does not have fixed last period when winding down is disabled
            if (!_windDown && subStake.lastPeriod == nextPeriod) {
                subStake.lastPeriod = 0;
                subStake.unlockingDuration = 1;
                continue;
            }
            // this sub-stake is no longer affected by winding down parameter
            if (subStake.lastPeriod != 0 || subStake.unlockingDuration == 0) {
                continue;
            }

            subStake.unlockingDuration = _windDown ? subStake.unlockingDuration - 1 : subStake.unlockingDuration + 1;
            if (subStake.unlockingDuration == 0) {
                subStake.lastPeriod = nextPeriod;
            }
        }
    }

    /**
    * @notice Activate/deactivate taking snapshots of balances
    * @param _enableSnapshots True to activate snapshots, False to deactivate
    */
    function setSnapshots(bool _enableSnapshots) external {
        StakerInfo storage info = stakerInfo[msg.sender];
        if (info.flags.bitSet(SNAPSHOTS_DISABLED_INDEX) == !_enableSnapshots) {
            return;
        }

        uint256 lastGlobalBalance = uint256(balanceHistory.lastValue());
        if(_enableSnapshots){
            info.history.addSnapshot(info.value);
            balanceHistory.addSnapshot(lastGlobalBalance + info.value);
        } else {
            info.history.addSnapshot(0);
            balanceHistory.addSnapshot(lastGlobalBalance - info.value);
        }
        info.flags = info.flags.toggleBit(SNAPSHOTS_DISABLED_INDEX);

        emit SnapshotSet(msg.sender, _enableSnapshots);
    }

    /**
    * @notice Adds a new snapshot to both the staker and global balance histories,
    * assuming the staker's balance was already changed
    * @param _info Reference to affected staker's struct
    * @param _addition Variance in balance. It can be positive or negative.
    */
    function addSnapshot(StakerInfo storage _info, int256 _addition) internal {
        if(!_info.flags.bitSet(SNAPSHOTS_DISABLED_INDEX)){
            _info.history.addSnapshot(_info.value);
            uint256 lastGlobalBalance = uint256(balanceHistory.lastValue());
            balanceHistory.addSnapshot(lastGlobalBalance.addSigned(_addition));
        }
    }

    /**
    * @notice Implementation of the receiveApproval(address,uint256,address,bytes) method
    * (see NuCypherToken contract). Deposit all tokens that were approved to transfer
    * @param _from Staker
    * @param _value Amount of tokens to deposit
    * @param _tokenContract Token contract address
    * @notice (param _extraData) Amount of periods during which tokens will be unlocked when wind down is enabled
    */
    function receiveApproval(
        address _from,
        uint256 _value,
        address _tokenContract,
        bytes calldata /* _extraData */
    )
        external
    {
        require(_tokenContract == address(token) && msg.sender == address(token));

        // Copy first 32 bytes from _extraData, according to calldata memory layout:
        //
        // 0x00: method signature      4 bytes
        // 0x04: _from                 32 bytes after encoding
        // 0x24: _value                32 bytes after encoding
        // 0x44: _tokenContract        32 bytes after encoding
        // 0x64: _extraData pointer    32 bytes. Value must be 0x80 (offset of _extraData wrt to 1st parameter)
        // 0x84: _extraData length     32 bytes
        // 0xA4: _extraData data       Length determined by previous variable
        //
        // See https://solidity.readthedocs.io/en/latest/abi-spec.html#examples

        uint256 payloadSize;
        uint256 payload;
        assembly {
            payloadSize := calldataload(0x84)
            payload := calldataload(0xA4)
        }
        payload = payload >> 8*(32 - payloadSize);
        deposit(_from, _from, MAX_SUB_STAKES, _value, uint16(payload));
    }

    /**
    * @notice Deposit tokens and create new sub-stake. Use this method to become a staker
    * @param _staker Staker
    * @param _value Amount of tokens to deposit
    * @param _unlockingDuration Amount of periods during which tokens will be unlocked when wind down is enabled
    */
    function deposit(address _staker, uint256 _value, uint16 _unlockingDuration) external {
        deposit(_staker, msg.sender, MAX_SUB_STAKES, _value, _unlockingDuration);
    }

    /**
    * @notice Deposit tokens and increase lock amount of an existing sub-stake
    * @dev This is preferable way to stake tokens because will be fewer active sub-stakes in the result
    * @param _index Index of the sub stake
    * @param _value Amount of tokens which will be locked
    */
    function depositAndIncrease(uint256 _index, uint256 _value) external onlyStaker {
        require(_index < MAX_SUB_STAKES);
        deposit(msg.sender, msg.sender, _index, _value, 0);
    }

    /**
    * @notice Deposit tokens
    * @dev Specify either index and zero periods (for an existing sub-stake)
    * or index >= MAX_SUB_STAKES and real value for periods (for a new sub-stake), not both
    * @param _staker Staker
    * @param _payer Owner of tokens
    * @param _index Index of the sub stake
    * @param _value Amount of tokens to deposit
    * @param _unlockingDuration Amount of periods during which tokens will be unlocked when wind down is enabled
    */
    function deposit(address _staker, address _payer, uint256 _index, uint256 _value, uint16 _unlockingDuration) internal {
        require(_value != 0);
        StakerInfo storage info = stakerInfo[_staker];
        // A staker can't be a worker for another staker
        require(stakerFromWorker[_staker] == address(0) || stakerFromWorker[_staker] == info.worker);
        // initial stake of the staker
        if (info.subStakes.length == 0 && info.lastCommittedPeriod == 0) {
            stakers.push(_staker);
            policyManager.register(_staker, getCurrentPeriod() - 1);
            info.flags = info.flags.toggleBit(MIGRATED_INDEX);
        }
        require(info.flags.bitSet(MIGRATED_INDEX));
        token.safeTransferFrom(_payer, address(this), _value);
        info.value += _value;
        lock(_staker, _index, _value, _unlockingDuration);

        addSnapshot(info, int256(_value));
        if (_index >= MAX_SUB_STAKES) {
            emit Deposited(_staker, _value, _unlockingDuration);
        } else {
            uint16 lastPeriod = getLastPeriodOfSubStake(_staker, _index);
            emit Deposited(_staker, _value, lastPeriod - getCurrentPeriod());
        }
    }

    /**
    * @notice Lock some tokens as a new sub-stake
    * @param _value Amount of tokens which will be locked
    * @param _unlockingDuration Amount of periods during which tokens will be unlocked when wind down is enabled
    */
    function lockAndCreate(uint256 _value, uint16 _unlockingDuration) external onlyStaker {
        lock(msg.sender, MAX_SUB_STAKES, _value, _unlockingDuration);
    }

    /**
    * @notice Increase lock amount of an existing sub-stake
    * @param _index Index of the sub-stake
    * @param _value Amount of tokens which will be locked
    */
    function lockAndIncrease(uint256 _index, uint256 _value) external onlyStaker {
        require(_index < MAX_SUB_STAKES);
        lock(msg.sender, _index, _value, 0);
    }

    /**
    * @notice Lock some tokens as a stake
    * @dev Specify either index and zero periods (for an existing sub-stake)
    * or index >= MAX_SUB_STAKES and real value for periods (for a new sub-stake), not both
    * @param _staker Staker
    * @param _index Index of the sub stake
    * @param _value Amount of tokens which will be locked
    * @param _unlockingDuration Amount of periods during which tokens will be unlocked when wind down is enabled
    */
    function lock(address _staker, uint256 _index, uint256 _value, uint16 _unlockingDuration) internal {
        if (_index < MAX_SUB_STAKES) {
            require(_value > 0);
        } else {
            require(_value >= minAllowableLockedTokens && _unlockingDuration >= minLockedPeriods);
        }

        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod + 1;
        StakerInfo storage info = stakerInfo[_staker];
        uint256 lockedTokens = getLockedTokens(info, currentPeriod, nextPeriod);
        uint256 requestedLockedTokens = _value.add(lockedTokens);
        require(requestedLockedTokens <= info.value && requestedLockedTokens <= maxAllowableLockedTokens);

        // next period is committed
        if (info.nextCommittedPeriod == nextPeriod) {
            lockedPerPeriod[nextPeriod] += _value;
            emit CommitmentMade(_staker, nextPeriod, _value);
        }

        // if index was provided then increase existing sub-stake
        if (_index < MAX_SUB_STAKES) {
            lockAndIncrease(info, currentPeriod, nextPeriod, _staker, _index, _value);
        // otherwise create new
        } else {
            lockAndCreate(info, nextPeriod, _staker, _value, _unlockingDuration);
        }
    }

    /**
    * @notice Lock some tokens as a new sub-stake
    * @param _info Staker structure
    * @param _nextPeriod Next period
    * @param _staker Staker
    * @param _value Amount of tokens which will be locked
    * @param _unlockingDuration Amount of periods during which tokens will be unlocked when wind down is enabled
    */
    function lockAndCreate(
        StakerInfo storage _info,
        uint16 _nextPeriod,
        address _staker,
        uint256 _value,
        uint16 _unlockingDuration
    )
        internal
    {
        uint16 duration = _unlockingDuration;
        // if winding down is enabled and next period is committed
        // then sub-stakes duration were decreased
        if (_info.nextCommittedPeriod == _nextPeriod && _info.flags.bitSet(WIND_DOWN_INDEX)) {
            duration -= 1;
        }
        saveSubStake(_info, _nextPeriod, 0, duration, _value);

        emit Locked(_staker, _value, _nextPeriod, _unlockingDuration);
    }

    /**
    * @notice Increase lock amount of an existing sub-stake
    * @dev Probably will be created a new sub-stake but it will be active only one period
    * @param _info Staker structure
    * @param _currentPeriod Current period
    * @param _nextPeriod Next period
    * @param _staker Staker
    * @param _index Index of the sub-stake
    * @param _value Amount of tokens which will be locked
    */
    function lockAndIncrease(
        StakerInfo storage _info,
        uint16 _currentPeriod,
        uint16 _nextPeriod,
        address _staker,
        uint256 _index,
        uint256 _value
    )
        internal
    {
        SubStakeInfo storage subStake = _info.subStakes[_index];
        (, uint16 lastPeriod) = checkLastPeriodOfSubStake(_info, subStake, _currentPeriod);

        // create temporary sub-stake for current or previous committed periods
        // to leave locked amount in this period unchanged
        if (_info.currentCommittedPeriod != 0 &&
            _info.currentCommittedPeriod <= _currentPeriod ||
            _info.nextCommittedPeriod != 0 &&
            _info.nextCommittedPeriod <= _currentPeriod)
        {
            saveSubStake(_info, subStake.firstPeriod, _currentPeriod, 0, subStake.lockedValue);
        }

        subStake.lockedValue += uint128(_value);
        // all new locks should start from the next period
        subStake.firstPeriod = _nextPeriod;

        emit Locked(_staker, _value, _nextPeriod, lastPeriod - _currentPeriod);
    }

    /**
    * @notice Checks that last period of sub-stake is greater than the current period
    * @param _info Staker structure
    * @param _subStake Sub-stake structure
    * @param _currentPeriod Current period
    * @return startPeriod Start period. Use in the calculation of the last period of the sub stake
    * @return lastPeriod Last period of the sub stake
    */
    function checkLastPeriodOfSubStake(
        StakerInfo storage _info,
        SubStakeInfo storage _subStake,
        uint16 _currentPeriod
    )
        internal view returns (uint16 startPeriod, uint16 lastPeriod)
    {
        startPeriod = getStartPeriod(_info, _currentPeriod);
        lastPeriod = getLastPeriodOfSubStake(_subStake, startPeriod);
        // The sub stake must be active at least in the next period
        require(lastPeriod > _currentPeriod);
    }

    /**
    * @notice Save sub stake. First tries to override inactive sub stake
    * @dev Inactive sub stake means that last period of sub stake has been surpassed and already rewarded
    * @param _info Staker structure
    * @param _firstPeriod First period of the sub stake
    * @param _lastPeriod Last period of the sub stake
    * @param _unlockingDuration Duration of the sub stake in periods
    * @param _lockedValue Amount of locked tokens
    */
    function saveSubStake(
        StakerInfo storage _info,
        uint16 _firstPeriod,
        uint16 _lastPeriod,
        uint16 _unlockingDuration,
        uint256 _lockedValue
    )
        internal
    {
        for (uint256 i = 0; i < _info.subStakes.length; i++) {
            SubStakeInfo storage subStake = _info.subStakes[i];
            if (subStake.lastPeriod != 0 &&
                (_info.currentCommittedPeriod == 0 ||
                subStake.lastPeriod < _info.currentCommittedPeriod) &&
                (_info.nextCommittedPeriod == 0 ||
                subStake.lastPeriod < _info.nextCommittedPeriod))
            {
                subStake.firstPeriod = _firstPeriod;
                subStake.lastPeriod = _lastPeriod;
                subStake.unlockingDuration = _unlockingDuration;
                subStake.lockedValue = uint128(_lockedValue);
                return;
            }
        }
        require(_info.subStakes.length < MAX_SUB_STAKES);
        _info.subStakes.push(SubStakeInfo(_firstPeriod, _lastPeriod, _unlockingDuration, uint128(_lockedValue)));
    }

    /**
    * @notice Divide sub stake into two parts
    * @param _index Index of the sub stake
    * @param _newValue New sub stake value
    * @param _additionalDuration Amount of periods for extending sub stake
    */
    function divideStake(uint256 _index, uint256 _newValue, uint16 _additionalDuration) external onlyStaker {
        StakerInfo storage info = stakerInfo[msg.sender];
        require(_newValue >= minAllowableLockedTokens && _additionalDuration > 0);
        SubStakeInfo storage subStake = info.subStakes[_index];
        uint16 currentPeriod = getCurrentPeriod();
        (, uint16 lastPeriod) = checkLastPeriodOfSubStake(info, subStake, currentPeriod);

        uint256 oldValue = subStake.lockedValue;
        subStake.lockedValue = uint128(oldValue.sub(_newValue));
        require(subStake.lockedValue >= minAllowableLockedTokens);
        uint16 requestedPeriods = subStake.unlockingDuration.add16(_additionalDuration);
        saveSubStake(info, subStake.firstPeriod, 0, requestedPeriods, _newValue);
        emit Divided(msg.sender, oldValue, lastPeriod, _newValue, _additionalDuration);
        emit Locked(msg.sender, _newValue, subStake.firstPeriod, requestedPeriods);
    }

    /**
    * @notice Prolong active sub stake
    * @param _index Index of the sub stake
    * @param _additionalDuration Amount of periods for extending sub stake
    */
    function prolongStake(uint256 _index, uint16 _additionalDuration) external onlyStaker {
        StakerInfo storage info = stakerInfo[msg.sender];
        // Incorrect parameters
        require(_additionalDuration > 0);
        SubStakeInfo storage subStake = info.subStakes[_index];
        uint16 currentPeriod = getCurrentPeriod();
        (uint16 startPeriod, uint16 lastPeriod) = checkLastPeriodOfSubStake(info, subStake, currentPeriod);

        subStake.unlockingDuration = subStake.unlockingDuration.add16(_additionalDuration);
        // if the sub stake ends in the next committed period then reset the `lastPeriod` field
        if (lastPeriod == startPeriod) {
            subStake.lastPeriod = 0;
        }
        // The extended sub stake must not be less than the minimum value
        require(uint32(lastPeriod - currentPeriod) + _additionalDuration >= minLockedPeriods);
        emit Locked(msg.sender, subStake.lockedValue, lastPeriod + 1, _additionalDuration);
        emit Prolonged(msg.sender, subStake.lockedValue, lastPeriod, _additionalDuration);
    }

    /**
    * @notice Merge two sub-stakes into one if their last periods are equal
    * @dev It's possible that both sub-stakes will be active after this transaction.
    * But only one of them will be active until next call `commitToNextPeriod` (in the next period)
    * @param _index1 Index of the first sub-stake
    * @param _index2 Index of the second sub-stake
    */
    function mergeStake(uint256 _index1, uint256 _index2) external onlyStaker {
        require(_index1 != _index2); // must be different sub-stakes

        StakerInfo storage info = stakerInfo[msg.sender];
        SubStakeInfo storage subStake1 = info.subStakes[_index1];
        SubStakeInfo storage subStake2 = info.subStakes[_index2];
        uint16 currentPeriod = getCurrentPeriod();

        (, uint16 lastPeriod1) = checkLastPeriodOfSubStake(info, subStake1, currentPeriod);
        (, uint16 lastPeriod2) = checkLastPeriodOfSubStake(info, subStake2, currentPeriod);
        // both sub-stakes must have equal last period to be mergeable
        require(lastPeriod1 == lastPeriod2);
        emit Merged(msg.sender, subStake1.lockedValue, subStake2.lockedValue, lastPeriod1);

        if (subStake1.firstPeriod == subStake2.firstPeriod) {
            subStake1.lockedValue += subStake2.lockedValue;
            subStake2.lastPeriod = 1;
            subStake2.unlockingDuration = 0;
        } else if (subStake1.firstPeriod > subStake2.firstPeriod) {
            subStake1.lockedValue += subStake2.lockedValue;
            subStake2.lastPeriod = subStake1.firstPeriod - 1;
            subStake2.unlockingDuration = 0;
        } else {
            subStake2.lockedValue += subStake1.lockedValue;
            subStake1.lastPeriod = subStake2.firstPeriod - 1;
            subStake1.unlockingDuration = 0;
        }
    }

    /**
    * @notice Remove unused sub-stake to decrease gas cost for several methods
    */
    function removeUnusedSubStake(uint16 _index) external onlyStaker {
        StakerInfo storage info = stakerInfo[msg.sender];

        uint256 lastIndex = info.subStakes.length - 1;
        SubStakeInfo storage subStake = info.subStakes[_index];
        require(subStake.lastPeriod != 0 &&
                (info.currentCommittedPeriod == 0 ||
                subStake.lastPeriod < info.currentCommittedPeriod) &&
                (info.nextCommittedPeriod == 0 ||
                subStake.lastPeriod < info.nextCommittedPeriod));

        if (_index != lastIndex) {
            SubStakeInfo storage lastSubStake = info.subStakes[lastIndex];
            subStake.firstPeriod = lastSubStake.firstPeriod;
            subStake.lastPeriod = lastSubStake.lastPeriod;
            subStake.unlockingDuration = lastSubStake.unlockingDuration;
            subStake.lockedValue = lastSubStake.lockedValue;
        }
        info.subStakes.pop();
    }

    /**
    * @notice Withdraw available amount of tokens to staker
    * @param _value Amount of tokens to withdraw
    */
    function withdraw(uint256 _value) external onlyStaker {
        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod + 1;
        StakerInfo storage info = stakerInfo[msg.sender];
        // the max locked tokens in most cases will be in the current period
        // but when the staker locks more then we should use the next period
        uint256 lockedTokens = Math.max(getLockedTokens(info, currentPeriod, nextPeriod),
            getLockedTokens(info, currentPeriod, currentPeriod));
        require(_value <= info.value.sub(lockedTokens));
        info.value -= _value;

        addSnapshot(info, - int256(_value));
        token.safeTransfer(msg.sender, _value);
        emit Withdrawn(msg.sender, _value);

        // unbond worker if staker withdraws last portion of NU
        if (info.value == 0 &&
            info.nextCommittedPeriod == 0 &&
            info.worker != address(0))
        {
            stakerFromWorker[info.worker] = address(0);
            info.worker = address(0);
            emit WorkerBonded(msg.sender, address(0), currentPeriod);
        }
    }

    /**
    * @notice Make a commitment to the next period and mint for the previous period
    */
    function commitToNextPeriod() external isInitialized {
        address staker = stakerFromWorker[msg.sender];
        StakerInfo storage info = stakerInfo[staker];
        // Staker must have a stake to make a commitment
        require(info.value > 0);
        // Only worker with real address can make a commitment
        require(msg.sender == tx.origin);

        migrate(staker);

        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod + 1;
        // the period has already been committed
        require(info.nextCommittedPeriod != nextPeriod);

        uint16 lastCommittedPeriod = getLastCommittedPeriod(staker);
        (uint16 processedPeriod1, uint16 processedPeriod2) = mint(staker);

        uint256 lockedTokens = getLockedTokens(info, currentPeriod, nextPeriod);
        require(lockedTokens > 0);
        lockedPerPeriod[nextPeriod] += lockedTokens;

        info.currentCommittedPeriod = info.nextCommittedPeriod;
        info.nextCommittedPeriod = nextPeriod;

        decreaseSubStakesDuration(info, nextPeriod);

        // staker was inactive for several periods
        if (lastCommittedPeriod < currentPeriod) {
            info.pastDowntime.push(Downtime(lastCommittedPeriod + 1, currentPeriod));
        }

        policyManager.ping(staker, processedPeriod1, processedPeriod2, nextPeriod);
        emit CommitmentMade(staker, nextPeriod, lockedTokens);
    }

    /**
    * @notice Migrate from the old period length to the new one. Can be done only once
    * @param _staker Staker
    */
    function migrate(address _staker) public {
        StakerInfo storage info = stakerInfo[_staker];
        // check that provided address is/was a staker
        require(info.subStakes.length != 0 || info.lastCommittedPeriod != 0);
        if (info.flags.bitSet(MIGRATED_INDEX)) {
            return;
        }

        // reset state
        info.currentCommittedPeriod = 0;
        info.nextCommittedPeriod = 0;
        // maintain case when no more sub-stakes and need to avoid re-registering this staker during deposit
        info.lastCommittedPeriod = 1;
        info.workerStartPeriod = recalculatePeriod(info.workerStartPeriod);
        delete info.pastDowntime;

        // recalculate all sub-stakes
        uint16 currentPeriod = getCurrentPeriod();
        for (uint256 i = 0; i < info.subStakes.length; i++) {
            SubStakeInfo storage subStake = info.subStakes[i];
            subStake.firstPeriod = recalculatePeriod(subStake.firstPeriod);
            // sub-stake has fixed last period
            if (subStake.lastPeriod != 0) {
                subStake.lastPeriod = recalculatePeriod(subStake.lastPeriod);
                if (subStake.lastPeriod == 0) {
                    subStake.lastPeriod = 1;
                }
                subStake.unlockingDuration = 0;
            // sub-stake has no fixed ending but possible that with new period length will have
            } else {
                uint16 oldCurrentPeriod = uint16(block.timestamp / genesisSecondsPerPeriod);
                uint16 lastPeriod = recalculatePeriod(oldCurrentPeriod + subStake.unlockingDuration);
                subStake.unlockingDuration = lastPeriod - currentPeriod;
                if (subStake.unlockingDuration == 0) {
                    subStake.lastPeriod = lastPeriod;
                }
            }
        }

        policyManager.migrate(_staker);
        info.flags = info.flags.toggleBit(MIGRATED_INDEX);
        emit Migrated(_staker, currentPeriod);
    }

    /**
    * @notice Decrease sub-stakes duration if `windDown` is enabled
    */
    function decreaseSubStakesDuration(StakerInfo storage _info, uint16 _nextPeriod) internal {
        if (!_info.flags.bitSet(WIND_DOWN_INDEX)) {
            return;
        }
        for (uint256 index = 0; index < _info.subStakes.length; index++) {
            SubStakeInfo storage subStake = _info.subStakes[index];
            if (subStake.lastPeriod != 0 || subStake.unlockingDuration == 0) {
                continue;
            }
            subStake.unlockingDuration--;
            if (subStake.unlockingDuration == 0) {
                subStake.lastPeriod = _nextPeriod;
            }
        }
    }

    /**
    * @notice Mint tokens for previous periods if staker locked their tokens and made a commitment
    */
    function mint() external onlyStaker {
        // save last committed period to the storage if both periods will be empty after minting
        // because we won't be able to calculate last committed period
        // see getLastCommittedPeriod(address)
        StakerInfo storage info = stakerInfo[msg.sender];
        uint16 previousPeriod = getCurrentPeriod() - 1;
        if (info.nextCommittedPeriod <= previousPeriod && info.nextCommittedPeriod != 0) {
            info.lastCommittedPeriod = info.nextCommittedPeriod;
        }
        (uint16 processedPeriod1, uint16 processedPeriod2) = mint(msg.sender);

        if (processedPeriod1 != 0 || processedPeriod2 != 0) {
            policyManager.ping(msg.sender, processedPeriod1, processedPeriod2, 0);
        }
    }

    /**
    * @notice Mint tokens for previous periods if staker locked their tokens and made a commitment
    * @param _staker Staker
    * @return processedPeriod1 Processed period: currentCommittedPeriod or zero
    * @return processedPeriod2 Processed period: nextCommittedPeriod or zero
    */
    function mint(address _staker) internal returns (uint16 processedPeriod1, uint16 processedPeriod2) {
        uint16 currentPeriod = getCurrentPeriod();
        uint16 previousPeriod = currentPeriod - 1;
        StakerInfo storage info = stakerInfo[_staker];

        if (info.nextCommittedPeriod == 0 ||
            info.currentCommittedPeriod == 0 &&
            info.nextCommittedPeriod > previousPeriod ||
            info.currentCommittedPeriod > previousPeriod) {
            return (0, 0);
        }

        uint16 startPeriod = getStartPeriod(info, currentPeriod);
        uint256 reward = 0;
        bool reStake = !info.flags.bitSet(RE_STAKE_DISABLED_INDEX);

        if (info.currentCommittedPeriod != 0) {
            reward = mint(info, info.currentCommittedPeriod, currentPeriod, startPeriod, reStake);
            processedPeriod1 = info.currentCommittedPeriod;
            info.currentCommittedPeriod = 0;
            if (reStake) {
                lockedPerPeriod[info.nextCommittedPeriod] += reward;
            }
        }
        if (info.nextCommittedPeriod <= previousPeriod) {
            reward += mint(info, info.nextCommittedPeriod, currentPeriod, startPeriod, reStake);
            processedPeriod2 = info.nextCommittedPeriod;
            info.nextCommittedPeriod = 0;
        }

        info.value += reward;
        if (info.flags.bitSet(MEASURE_WORK_INDEX)) {
            info.completedWork += reward;
        }

        addSnapshot(info, int256(reward));
        emit Minted(_staker, previousPeriod, reward);
    }

    /**
    * @notice Calculate reward for one period
    * @param _info Staker structure
    * @param _mintingPeriod Period for minting calculation
    * @param _currentPeriod Current period
    * @param _startPeriod Pre-calculated start period
    */
    function mint(
        StakerInfo storage _info,
        uint16 _mintingPeriod,
        uint16 _currentPeriod,
        uint16 _startPeriod,
        bool _reStake
    )
        internal returns (uint256 reward)
    {
        reward = 0;
        for (uint256 i = 0; i < _info.subStakes.length; i++) {
            SubStakeInfo storage subStake =  _info.subStakes[i];
            uint16 lastPeriod = getLastPeriodOfSubStake(subStake, _startPeriod);
            if (subStake.firstPeriod <= _mintingPeriod && lastPeriod >= _mintingPeriod) {
                uint256 subStakeReward = mint(
                    _currentPeriod,
                    subStake.lockedValue,
                    lockedPerPeriod[_mintingPeriod],
                    lastPeriod.sub16(_mintingPeriod));
                reward += subStakeReward;
                if (_reStake) {
                    subStake.lockedValue += uint128(subStakeReward);
                }
            }
        }
        return reward;
    }

    //-------------------------Slashing-------------------------
    /**
    * @notice Slash the staker's stake and reward the investigator
    * @param _staker Staker's address
    * @param _penalty Penalty
    * @param _investigator Investigator
    * @param _reward Reward for the investigator
    */
    function slashStaker(
        address _staker,
        uint256 _penalty,
        address _investigator,
        uint256 _reward
    )
        public isInitialized
    {
        require(msg.sender == address(adjudicator));
        require(_penalty > 0);
        StakerInfo storage info = stakerInfo[_staker];
        require(info.flags.bitSet(MIGRATED_INDEX));
        if (info.value <= _penalty) {
            _penalty = info.value;
        }
        info.value -= _penalty;
        if (_reward > _penalty) {
            _reward = _penalty;
        }

        uint16 currentPeriod = getCurrentPeriod();
        uint16 nextPeriod = currentPeriod + 1;
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
        if (_penalty > _reward) {
            unMint(_penalty - _reward);
        }
        // TODO change to withdrawal pattern (#1499)
        if (_reward > 0) {
            token.safeTransfer(_investigator, _reward);
        }

        addSnapshot(info, - int256(_penalty));

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
    */
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
        currentLock = 0;
        nextLock = 0;
        currentAndNextLock = 0;

        for (uint256 i = 0; i < _info.subStakes.length; i++) {
            SubStakeInfo storage subStake = _info.subStakes[i];
            uint16 lastPeriod = getLastPeriodOfSubStake(subStake, _startPeriod);
            if (lastPeriod < subStake.firstPeriod) {
                continue;
            }
            if (subStake.firstPeriod <= _currentPeriod &&
                lastPeriod >= _nextPeriod) {
                currentAndNextLock += subStake.lockedValue;
            } else if (subStake.firstPeriod <= _currentPeriod &&
                lastPeriod >= _currentPeriod) {
                currentLock += subStake.lockedValue;
            } else if (subStake.firstPeriod <= _nextPeriod &&
                lastPeriod >= _nextPeriod) {
                nextLock += subStake.lockedValue;
            }
            uint16 duration = lastPeriod - subStake.firstPeriod;
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
    */
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
                minSubStakeDuration = minSubStakeLastPeriod - shortestSubStake.firstPeriod;
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
                shortestSubStake.lockedValue -= uint128(_penalty);
                saveOldSubStake(_info, shortestSubStake.firstPeriod, _penalty, _decreasePeriod);
                _penalty = 0;
            } else {
                shortestSubStake.lastPeriod = _decreasePeriod - 1;
                _penalty -= shortestSubStake.lockedValue;
                appliedPenalty = shortestSubStake.lockedValue;
            }
            if (_info.currentCommittedPeriod >= _decreasePeriod &&
                _info.currentCommittedPeriod <= minSubStakeLastPeriod)
            {
                lockedPerPeriod[_info.currentCommittedPeriod] -= appliedPenalty;
            }
            if (_info.nextCommittedPeriod >= _decreasePeriod &&
                _info.nextCommittedPeriod <= minSubStakeLastPeriod)
            {
                lockedPerPeriod[_info.nextCommittedPeriod] -= appliedPenalty;
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
    */
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
            uint16 duration = lastPeriod - subStake.firstPeriod;
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
    * @dev Saving happens only if the previous period is committed
    * @param _info Staker structure
    * @param _firstPeriod First period of the old sub stake
    * @param _lockedValue Locked value of the old sub stake
    * @param _currentPeriod Current period, when the old sub stake is already unlocked
    */
    function saveOldSubStake(
        StakerInfo storage _info,
        uint16 _firstPeriod,
        uint256 _lockedValue,
        uint16 _currentPeriod
    )
        internal
    {
        // Check that the old sub stake should be saved
        bool oldCurrentCommittedPeriod = _info.currentCommittedPeriod != 0 &&
            _info.currentCommittedPeriod < _currentPeriod;
        bool oldnextCommittedPeriod = _info.nextCommittedPeriod != 0 &&
            _info.nextCommittedPeriod < _currentPeriod;
        bool crosscurrentCommittedPeriod = oldCurrentCommittedPeriod && _info.currentCommittedPeriod >= _firstPeriod;
        bool crossnextCommittedPeriod = oldnextCommittedPeriod && _info.nextCommittedPeriod >= _firstPeriod;
        if (!crosscurrentCommittedPeriod && !crossnextCommittedPeriod) {
            return;
        }
        // Try to find already existent proper old sub stake
        uint16 previousPeriod = _currentPeriod - 1;
        for (uint256 i = 0; i < _info.subStakes.length; i++) {
            SubStakeInfo storage subStake = _info.subStakes[i];
            if (subStake.lastPeriod == previousPeriod &&
                ((crosscurrentCommittedPeriod ==
                (oldCurrentCommittedPeriod && _info.currentCommittedPeriod >= subStake.firstPeriod)) &&
                (crossnextCommittedPeriod ==
                (oldnextCommittedPeriod && _info.nextCommittedPeriod >= subStake.firstPeriod))))
            {
                subStake.lockedValue += uint128(_lockedValue);
                return;
            }
        }
        saveSubStake(_info, _firstPeriod, previousPeriod, 0, _lockedValue);
    }

    //-------------Additional getters for stakers info-------------
    /**
    * @notice Return the length of the array of stakers
    */
    function getStakersLength() external view returns (uint256) {
        return stakers.length;
    }

    /**
    * @notice Return the length of the array of sub stakes
    */
    function getSubStakesLength(address _staker) external view returns (uint256) {
        return stakerInfo[_staker].subStakes.length;
    }

    /**
    * @notice Return the information about sub stake
    */
    function getSubStakeInfo(address _staker, uint256 _index)
    // TODO change to structure when ABIEncoderV2 is released (#1501)
//        public view returns (SubStakeInfo)
        // TODO "virtual" only for tests, probably will be removed after #1512
        external view virtual returns (
            uint16 firstPeriod,
            uint16 lastPeriod,
            uint16 unlockingDuration,
            uint128 lockedValue
        )
    {
        SubStakeInfo storage info = stakerInfo[_staker].subStakes[_index];
        firstPeriod = info.firstPeriod;
        lastPeriod = info.lastPeriod;
        unlockingDuration = info.unlockingDuration;
        lockedValue = info.lockedValue;
    }

    /**
    * @notice Return the length of the array of past downtime
    */
    function getPastDowntimeLength(address _staker) external view returns (uint256) {
        return stakerInfo[_staker].pastDowntime.length;
    }

    /**
    * @notice Return the information about past downtime
    */
    function  getPastDowntime(address _staker, uint256 _index)
    // TODO change to structure when ABIEncoderV2 is released (#1501)
//        public view returns (Downtime)
        external view returns (uint16 startPeriod, uint16 endPeriod)
    {
        Downtime storage downtime = stakerInfo[_staker].pastDowntime[_index];
        startPeriod = downtime.startPeriod;
        endPeriod = downtime.endPeriod;
    }

    //------------------ ERC900 connectors ----------------------

    function totalStakedForAt(address _owner, uint256 _blockNumber) public view override returns (uint256){
        return stakerInfo[_owner].history.getValueAt(_blockNumber);
    }

    function totalStakedAt(uint256 _blockNumber) public view override returns (uint256){
        return balanceHistory.getValueAt(_blockNumber);
    }

    function supportsHistory() external pure override returns (bool){
        return true;
    }

    //------------------------Upgradeable------------------------
    /**
    * @dev Get StakerInfo structure by delegatecall
    */
    function delegateGetStakerInfo(address _target, bytes32 _staker)
        internal returns (StakerInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, this.stakerInfo.selector, 1, _staker, 0);
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get SubStakeInfo structure by delegatecall
    */
    function delegateGetSubStakeInfo(address _target, bytes32 _staker, uint256 _index)
        internal returns (SubStakeInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(
            _target, this.getSubStakeInfo.selector, 2, _staker, bytes32(_index));
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get Downtime structure by delegatecall
    */
    function delegateGetPastDowntime(address _target, bytes32 _staker, uint256 _index)
        internal returns (Downtime memory result)
    {
        bytes32 memoryAddress = delegateGetData(
            _target, this.getPastDowntime.selector, 2, _staker, bytes32(_index));
        assembly {
            result := memoryAddress
        }
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `verifyState`
    function verifyState(address _testTarget) public override virtual {
        super.verifyState(_testTarget);
        require(delegateGet(_testTarget, this.lockedPerPeriod.selector,
            bytes32(bytes2(RESERVED_PERIOD))) == lockedPerPeriod[RESERVED_PERIOD]);
        require(address(delegateGet(_testTarget, this.stakerFromWorker.selector, bytes32(0))) ==
            stakerFromWorker[address(0)]);

        require(delegateGet(_testTarget, this.getStakersLength.selector) == stakers.length);
        if (stakers.length == 0) {
            return;
        }
        address stakerAddress = stakers[0];
        require(address(uint160(delegateGet(_testTarget, this.stakers.selector, 0))) == stakerAddress);
        StakerInfo storage info = stakerInfo[stakerAddress];
        bytes32 staker = bytes32(uint256(stakerAddress));
        StakerInfo memory infoToCheck = delegateGetStakerInfo(_testTarget, staker);
        require(infoToCheck.value == info.value &&
            infoToCheck.currentCommittedPeriod == info.currentCommittedPeriod &&
            infoToCheck.nextCommittedPeriod == info.nextCommittedPeriod &&
            infoToCheck.flags == info.flags &&
            infoToCheck.lastCommittedPeriod == info.lastCommittedPeriod &&
            infoToCheck.completedWork == info.completedWork &&
            infoToCheck.worker == info.worker &&
            infoToCheck.workerStartPeriod == info.workerStartPeriod);

        require(delegateGet(_testTarget, this.getPastDowntimeLength.selector, staker) ==
            info.pastDowntime.length);
        for (uint256 i = 0; i < info.pastDowntime.length && i < MAX_CHECKED_VALUES; i++) {
            Downtime storage downtime = info.pastDowntime[i];
            Downtime memory downtimeToCheck = delegateGetPastDowntime(_testTarget, staker, i);
            require(downtimeToCheck.startPeriod == downtime.startPeriod &&
                downtimeToCheck.endPeriod == downtime.endPeriod);
        }

        require(delegateGet(_testTarget, this.getSubStakesLength.selector, staker) == info.subStakes.length);
        for (uint256 i = 0; i < info.subStakes.length && i < MAX_CHECKED_VALUES; i++) {
            SubStakeInfo storage subStakeInfo = info.subStakes[i];
            SubStakeInfo memory subStakeInfoToCheck = delegateGetSubStakeInfo(_testTarget, staker, i);
            require(subStakeInfoToCheck.firstPeriod == subStakeInfo.firstPeriod &&
                subStakeInfoToCheck.lastPeriod == subStakeInfo.lastPeriod &&
                subStakeInfoToCheck.unlockingDuration == subStakeInfo.unlockingDuration &&
                subStakeInfoToCheck.lockedValue == subStakeInfo.lockedValue);
        }

        // it's not perfect because checks not only slot value but also decoding
        // at least without additional functions
        require(delegateGet(_testTarget, this.totalStakedForAt.selector, staker, bytes32(block.number)) ==
            totalStakedForAt(stakerAddress, block.number));
        require(delegateGet(_testTarget, this.totalStakedAt.selector, bytes32(block.number)) ==
            totalStakedAt(block.number));

        if (info.worker != address(0)) {
            require(address(delegateGet(_testTarget, this.stakerFromWorker.selector, bytes32(uint256(info.worker)))) ==
                stakerFromWorker[info.worker]);
        }
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `finishUpgrade`
    function finishUpgrade(address _target) public override virtual {
        super.finishUpgrade(_target);
        // Create fake period
        lockedPerPeriod[RESERVED_PERIOD] = 111;

        // Create fake worker
        stakerFromWorker[address(0)] = address(this);
    }
}
