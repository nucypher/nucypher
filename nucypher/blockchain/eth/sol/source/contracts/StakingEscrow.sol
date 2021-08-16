// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0; // TODO


import "aragon/interfaces/IERC900History.sol";
import "contracts/NuCypherToken.sol";
import "contracts/lib/Bits.sol";
import "contracts/lib/Snapshot.sol";
import "contracts/lib/AdditionalMath.sol";
import "contracts/proxy/Upgradeable.sol";
import "zeppelin/math/SafeMath.sol";
import "zeppelin/math/Math.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";
import "zeppelin/token/ERC20/IERC20.sol";


/**
* @notice TToken interface
*/
interface TTokenInterface is IERC20 {
    function nuToT(uint256 _amount) external view returns (uint256);
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
* @dev |v1.1.0|
*/
contract StakingEscrowStub is Upgradeable {
    NuCypherToken public immutable token;
    uint256 public immutable minAllowableLockedTokens;
    uint256 public immutable maxAllowableLockedTokens;

    /**
    * @notice Predefines some variables for use when deploying other contracts
    * @param _token Token contract
    * @param _minAllowableLockedTokens Min amount of tokens that can be locked
    * @param _maxAllowableLockedTokens Max amount of tokens that can be locked
    */
    constructor(
        NuCypherToken _token,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens
    ) {
        require(_token.totalSupply() > 0 &&
            _maxAllowableLockedTokens != 0);

        token = _token;
        minAllowableLockedTokens = _minAllowableLockedTokens;
        maxAllowableLockedTokens = _maxAllowableLockedTokens;
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `verifyState`
    function verifyState(address _testTarget) public override virtual {
        super.verifyState(_testTarget);

        // we have to use real values even though this is a stub
        require(address(delegateGet(_testTarget, this.token.selector)) == address(token));
        require(delegateGet(_testTarget, this.minAllowableLockedTokens.selector) == minAllowableLockedTokens);
        require(delegateGet(_testTarget, this.maxAllowableLockedTokens.selector) == maxAllowableLockedTokens);
    }
}


/**
* @title StakingEscrow
* @notice Contract holds and locks stakers tokens.
* Each staker that locks their tokens will receive some compensation
* @dev |v6.1.1|
*/
contract StakingEscrow is Upgradeable, IERC900History {

    using AdditionalMath for uint256;
//    using AdditionalMath for uint32;
//    using AdditionalMath for uint16;
    using Bits for uint256;
    using SafeMath for uint256;
    using Snapshot for uint128[];
    using SafeERC20 for NuCypherToken;
    using SafeERC20 for TTokenInterface;

    // TODO docs
    event RewardAdded(uint256 reward);
    event RewardPaid(address indexed staker, uint256 reward);

    /**
    * @notice Signals that tokens were deposited
    * @param staker Staker address
    * @param value Amount deposited (in NuNits)
    */
    event Deposited(address indexed staker, uint256 value);

    /**
    * @notice Signals that NU tokens were withdrawn to the staker
    * @param staker Staker address
    * @param value Amount withdraws (in NuNits)
    */
    event NUWithdrawn(address indexed staker, uint256 value);

    /**
    * @notice Signals that T tokens were withdrawn to the staker
    * @param staker Staker address
    * @param value Amount withdraws (in NuNits)
    */
    event TWithdrawn(address indexed staker, uint256 value);

    /**
    * @notice Signals that the staker was slashed
    * @param staker Staker address
    * @param penalty Slashing penalty
    * @param investigator Investigator address
    * @param reward Value of reward provided to investigator (in NuNits)
    */
    event Slashed(address indexed staker, uint256 penalty, address indexed investigator, uint256 reward);

    /**
    * @notice Signals that a worker was bonded to the staker
    * @param staker Staker address
    * @param worker Worker address
    */
    event WorkerBonded(address indexed staker, address indexed worker);

    /// internal event
    event WorkMeasurementSet(address indexed staker, bool measureWork);

    struct StakerInfo {
        uint256 nuValue;
        uint16 stub1; // former slot for currentCommittedPeriod // TODO combine 4 slots?
        uint16 stub2; // former slot for nextCommittedPeriod
        uint16 stub3; // former slot for lastCommittedPeriod
        uint16 stub4; // former slot for lockReStakeUntilPeriod
        uint256 completedWork;
        uint16 stub5; // former slot for workerStartPeriod
        address worker;
        uint256 flags; // uint256 to acquire whole slot and minimize operations on it

        uint256 workerStartTimestamp;
        uint256 tValue;
        uint256 startUnstakingTimestamp;
        uint256 tReward;
        uint256 rewardPerTokenPaid;

        uint256[] stub6; // former slot for pastDowntime
        uint256[] stub7; // former slot for subStakes
        uint128[] history; // TODO two snapshots?

    }

    uint128 constant MAX_UINT128 = uint128(0) - 1;

    // used only for upgrading
    uint16 internal constant RESERVED_PERIOD = 0;
//    uint16 internal constant MAX_CHECKED_VALUES = 5;
    uint16 internal constant MAX_UINT16 = 65535;

    // indices for flags
    uint8 internal constant RE_STAKE_DISABLED_INDEX = 0;
    uint8 internal constant WIND_DOWN_INDEX = 1;
    uint8 internal constant MEASURE_WORK_INDEX = 2;
    uint8 internal constant SNAPSHOTS_DISABLED_INDEX = 3;
    uint8 internal constant MIGRATED_INDEX = 4;

    uint128 public immutable formerTotalNUSupply;

    uint256 public immutable minWorkerSeconds;
    uint256 public immutable minAllowableLockedTokens;
    uint256 public immutable maxAllowableLockedTokens;

    uint256 public immutable minUnstakingDuration;
    uint256 public immutable rewardDuration;

    NuCypherToken public immutable nuToken;
    TTokenInterface public immutable tToken;
    AdjudicatorInterface public immutable adjudicator;
    WorkLockInterface public immutable workLock;

    uint128 stub1; // former slot for previousPeriodSupply
    uint128 totalNUSupply; // former slot for currentPeriodSupply
    uint16 stub2; // former slot for currentMintingPeriod

    mapping (address => StakerInfo) public stakerInfo;
    address[] public stakers;
    mapping (address => address) public stakerFromWorker;

    mapping (uint16 => uint256) stub3; // former slot for lockedPerPeriod
    uint128[] public balanceHistory;

    address stub4; // former slot for PolicyManager
    address stub5; // former slot for Adjudicator
    address stub6; // former slot for WorkLock

    mapping (uint16 => uint256) stub7; // last former slot for lockedPerPeriod

    uint256 public totalNUStaked;
    uint256 public totalTStaked;

    uint256 public periodFinish = 0;
    uint256 public rewardRate = 0;
    uint256 public lastUpdateTime;
    uint256 public rewardPerTokenStored;

    /**
    * @notice Constructor sets address of token contract and parameters for staking
    * @param _nuToken NuCypher token contract
    * @param _tToken T token contract
    * @param _adjudicator Adjudicator contract
    * @param _workLock WorkLock contract. Zero address if there is no WorkLock
    * @param _minAllowableLockedTokens Min amount of tokens that can be locked
    * @param _maxAllowableLockedTokens Max amount of tokens that can be locked
    * @param _minWorkerSeconds Min amount of seconds while a worker can't be changed
     * @param _minUnstakingDuration Min unstaking duration (in sec) to be eligible for staking
     * @param _rewardDuration Duration of one reward cycle
    */
    constructor(
        NuCypherToken _nuToken,
        TTokenInterface _tToken,
        AdjudicatorInterface _adjudicator,
        WorkLockInterface _workLock,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens,
        uint256 _minWorkerSeconds,
        uint256 _minUnstakingDuration,
        uint256 _rewardDuration
    )
    {
        require(_maxAllowableLockedTokens != 0 && _rewardDuration != 0);
        minAllowableLockedTokens = _minAllowableLockedTokens;
        maxAllowableLockedTokens = _maxAllowableLockedTokens;
        minWorkerSeconds = _minWorkerSeconds;
        minUnstakingDuration = _minUnstakingDuration;
        rewardDuration = _rewardDuration;

        uint256 localNUTotalSupply = _nuToken.totalSupply();
        require(localNUTotalSupply > 0 &&
            _tToken.totalSupply() > 0 &&
            _adjudicator.rewardCoefficient() != 0 &&
            (address(_workLock) == address(0) || _workLock.token() == _nuToken));

        formerTotalNUSupply = uint128(localNUTotalSupply);
        nuToken = _nuToken;
        tToken = _tToken;
        adjudicator = _adjudicator;
        workLock = _workLock;
    }

    /**
    * @dev Checks the existence of a staker in the contract
    */
    modifier onlyStaker()
    {
        StakerInfo storage info = stakerInfo[msg.sender];
        require(info.nuValue > 0 || info.tValue > 0);
        _;
    }

    modifier updateReward(address _staker) {
        rewardPerTokenStored = rewardPerToken();
        lastUpdateTime = lastTimeRewardApplicable();
        if (_staker != address(0)) {
            StakerInfo storage info = stakerInfo[_staker];
            info.tReward = earned(_staker);
            info.rewardPerTokenPaid = rewardPerTokenStored;
        }
        _;
    }

    //------------------------Reward------------------------------

    function totalStaked() public view returns (uint256) {
        return totalTStaked + tToken.nuToT(totalNUStaked);
    }

    function lastTimeRewardApplicable() public view returns (uint256) {
        return Math.min(block.timestamp, periodFinish);
    }

    function rewardPerToken() public view returns (uint256) {
        uint256 staked = totalStaked();
        if (staked == 0) {
            return rewardPerTokenStored;
        }
        return
            rewardPerTokenStored.add(
                lastTimeRewardApplicable()
                    .sub(lastUpdateTime)
                    .mul(rewardRate)
                    .mul(1e18)
                    .div(staked)
            );
    }

    function earned(address _staker) public view returns (uint256) {
        StakerInfo storage info = stakerInfo[_staker];
        return
            getStakedTokens(_staker)
                .mul(rewardPerToken().sub(info.rewardPerTokenPaid))
                .div(1e18)
                .add(info.tReward);
    }

    function withdrawReward() public updateReward(msg.sender) {
        uint256 reward = earned(msg.sender);
        if (reward > 0) {
            stakerInfo[msg.sender].tReward = 0;
            tToken.safeTransfer(msg.sender, reward);
            emit RewardPaid(msg.sender, reward);
        }
    }

    function pushReward(uint256 _reward) external updateReward(address(0)) {
        require(_reward > 0);
        tToken.safeTransfer(msg.sender, _reward);
        if (block.timestamp >= periodFinish) {
            rewardRate = _reward.div(rewardDuration);
        } else {
            uint256 remaining = periodFinish.sub(block.timestamp);
            uint256 leftover = remaining.mul(rewardRate);
            rewardRate = _reward.add(leftover).div(rewardDuration);
        }
        lastUpdateTime = block.timestamp;
        periodFinish = block.timestamp.add(rewardDuration);
        emit RewardAdded(_reward);
    }

    //------------------------Main getters------------------------
    /**
    * @notice Get all tokens belonging to the staker
    */
    function getAllTokens(address _staker) external view returns (uint256) {
        StakerInfo storage info = stakerInfo[_staker];
        return info.tValue.add(tToken.nuToT(info.nuValue)).add(info.tReward);
    }

    /**
    * @notice Get all tokens belonging to the staker
    */
    function getStakedTokens(address _staker) public view returns (uint256) {
        StakerInfo storage info = stakerInfo[_staker];
        return info.tValue.add(tToken.nuToT(info.nuValue));
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
    * @notice Get the value of staked tokens for active stakers as well as stakers and their staked tokens
    * @param _startIndex Start index for looking in stakers array
    * @param _maxStakers Max stakers for looking, if set 0 then all will be used
    * @return allStakedTokens Sum of staked tokens for active stakers
    * @return activeStakers Array of stakers and their staked tokens. Stakers addresses stored as uint256
    * @dev Note that activeStakers[0] in an array of uint256, but you want addresses. Careful when used directly!
    */
    function getActiveStakers(uint256 _startIndex, uint256 _maxStakers)
        external view returns (uint256 allStakedTokens, uint256[2][] memory activeStakers)
    {
        uint256 endIndex = stakers.length;
        require(_startIndex < endIndex);
        if (_maxStakers != 0 && _startIndex + _maxStakers < endIndex) {
            endIndex = _startIndex + _maxStakers;
        }
        activeStakers = new uint256[2][](endIndex - _startIndex);
        allStakedTokens = 0;

        uint256 resultIndex = 0;
        for (uint256 i = _startIndex; i < endIndex; i++) {
            address staker = stakers[i];
            StakerInfo storage info = stakerInfo[staker];
            if ((info.nuValue == 0 && info.tValue == 0) || info.startUnstakingTimestamp != 0) {
                continue;
            }
            uint256 staked = getStakedTokens(staker);
            activeStakers[resultIndex][0] = uint256(staker);
            activeStakers[resultIndex++][1] = staked;
            allStakedTokens = allStakedTokens.add(staked);
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
        if (info.worker != address(0)) { // If this staker had a worker ...
            // Check that enough time has passed to change it
            require(block.timestamp >= info.workerStartTimestamp.add(minWorkerSeconds));
            // Remove the old relation "worker->staker"
            stakerFromWorker[info.worker] = address(0);
        }

        if (_worker != address(0)) {
            // Specified worker is already in use
            require(stakerFromWorker[_worker] == address(0));
            // Specified worker is a staker
            require(stakerInfo[_worker].nuValue == 0 || stakerInfo[_worker].tValue == 0 || _worker == msg.sender);
            // Set new worker->staker relation
            stakerFromWorker[_worker] = msg.sender;
        }

        // Bond new worker (or unbond if _worker == address(0))
        info.worker = _worker;
        info.workerStartTimestamp = block.timestamp;
        emit WorkerBonded(msg.sender, _worker);
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
        deposit(_staker, msg.sender, _value);
    }


    /**
    * @notice Adds a new snapshot to both the staker and global balance histories,
    * assuming the staker's balance was already changed
    * @param _info Reference to affected staker's struct
    * @param _addition Variance in balance. It can be positive or negative.
    */
    function addSnapshot(StakerInfo storage _info, int256 _addition) internal {
        if(!_info.flags.bitSet(SNAPSHOTS_DISABLED_INDEX)){
            _info.history.addSnapshot(_info.nuValue);
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
        require(_tokenContract == address(nuToken) && msg.sender == address(nuToken));
        deposit(_from, _from, _value);
    }

    /**
    * @notice Deposit tokens and create new sub-stake. Use this method to become a staker
    * @param _staker Staker
    * @param _value Amount of tokens to deposit
    */
    function deposit(address _staker, uint256 _value) external {
        deposit(_staker, msg.sender, _value);
    }

    /**
    * @notice Deposit T tokens
    * @param _staker Staker
    * @param _payer Owner of tokens
    * @param _value Amount of tokens to deposit
    */
    function deposit(address _staker, address _payer, uint256 _value) internal updateReward(_staker) {
        require(_value != 0);
        StakerInfo storage info = stakerInfo[_staker];
        // A staker can't be a worker for another staker
        require(stakerFromWorker[_staker] == address(0) || stakerFromWorker[_staker] == info.worker);
        require(info.startUnstakingTimestamp == 0); // TODO allow to topup after unstaking?
        // initial stake of the staker
        if (info.nuValue == 0 && info.tValue == 0 && info.workerStartTimestamp == 0) { // TODO ???
            stakers.push(_staker);
        }
        tToken.safeTransferFrom(_payer, address(this), _value);
        info.tValue += _value;
        totalTStaked += _value;

        addSnapshot(info, int256(_value));
        emit Deposited(_staker, _value);
    }

    /**
    * @notice Start unstaking process
    */
    function startUnstaking() external {
        StakerInfo storage info = stakerInfo[msg.sender];
        require((info.nuValue > 0 || info.tValue > 0) && info.startUnstakingTimestamp == 0); // TODO extract
        info.startUnstakingTimestamp = block.timestamp;
    }

    /**
    * @notice Withdraw available amount of NU tokens to staker
    * @param _value Amount of tokens to withdraw
    */
    function withdrawNU(uint256 _value) external onlyStaker updateReward(msg.sender) {
        StakerInfo storage info = stakerInfo[msg.sender];
        require(_value <= info.nuValue &&
                info.startUnstakingTimestamp + minUnstakingDuration >= block.timestamp);
        info.nuValue -= _value;
        totalNUStaked -= _value; // TODO protection?
        if (info.nuValue == 0 && info.tValue == 0) {
            info.startUnstakingTimestamp = 0;
        }

        addSnapshot(info, - int256(_value)); // TODO
        nuToken.safeTransfer(msg.sender, _value);
        emit NUWithdrawn(msg.sender, _value);

        autoUnbondWorker(msg.sender, info);
    }

    /**
    * @notice Withdraw available amount of T tokens to staker
    * @param _value Amount of tokens to withdraw
    */
    function withdrawT(uint256 _value) external onlyStaker updateReward(msg.sender) {
        StakerInfo storage info = stakerInfo[msg.sender];
        require(_value <= info.tValue &&
                info.startUnstakingTimestamp + minUnstakingDuration >= block.timestamp);
        info.tValue -= _value;
        totalTStaked -= _value;
        if (info.nuValue == 0 && info.tValue == 0) {
            info.startUnstakingTimestamp = 0;
        }

        addSnapshot(info, - int256(_value)); // TODO
        tToken.safeTransfer(msg.sender, _value);
        emit TWithdrawn(msg.sender, _value);

        autoUnbondWorker(msg.sender, info);
    }

    /**
    * @notice Unbond worker if staker withdraws last portion of NU and T
    */
    function autoUnbondWorker(address _staker, StakerInfo storage _info) internal {
        if (_info.nuValue == 0 &&
            _info.tValue == 0 &&
            _info.worker != address(0))
        {
            stakerFromWorker[_info.worker] = address(0);
            _info.worker = address(0);
            emit WorkerBonded(_staker, address(0));
        }
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
        external updateReward(_staker)
    {
        // TODO
//        require(msg.sender == address(adjudicator));
//        require(_penalty > 0);
//        StakerInfo storage info = stakerInfo[_staker];
//        require(info.flags.bitSet(MIGRATED_INDEX));
//        if (info.nuValue <= _penalty) {
//            _penalty = info.nuValue;
//        }
//        info.nuValue -= _penalty;
//        if (_reward > _penalty) {
//            _reward = _penalty;
//        }
//
//        emit Slashed(_staker, _penalty, _investigator, _reward);
//        if (_penalty > _reward) {
//            unMint(_penalty - _reward);
//        }
//        // TODO change to withdrawal pattern (#1499)
//        if (_reward > 0) {
//            nuToken.safeTransfer(_investigator, _reward);
//        }
//
//        addSnapshot(info, - int256(_penalty));

    }

    //-------------Additional getters for stakers info-------------
    /**
    * @notice Return the length of the array of stakers
    */
    function getStakersLength() external view returns (uint256) {
        return stakers.length;
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

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `verifyState`
    function verifyState(address _testTarget) public override virtual {
        super.verifyState(_testTarget);
//        require(delegateGet(_testTarget, this.lockedPerPeriod.selector,
//            bytes32(bytes2(RESERVED_PERIOD))) == lockedPerPeriod[RESERVED_PERIOD]);
//        require(address(delegateGet(_testTarget, this.stakerFromWorker.selector, bytes32(0))) ==
//            stakerFromWorker[address(0)]);
//
//        require(delegateGet(_testTarget, this.getStakersLength.selector) == stakers.length);
//        if (stakers.length == 0) {
//            return;
//        }
//        address stakerAddress = stakers[0];
//        require(address(uint160(delegateGet(_testTarget, this.stakers.selector, 0))) == stakerAddress);
//        StakerInfo storage info = stakerInfo[stakerAddress];
//        bytes32 staker = bytes32(uint256(stakerAddress));
//        StakerInfo memory infoToCheck = delegateGetStakerInfo(_testTarget, staker);
//        require(infoToCheck.nuValue == info.nuValue &&
//            infoToCheck.currentCommittedPeriod == info.currentCommittedPeriod &&
//            infoToCheck.nextCommittedPeriod == info.nextCommittedPeriod &&
//            infoToCheck.flags == info.flags &&
//            infoToCheck.lastCommittedPeriod == info.lastCommittedPeriod &&
//            infoToCheck.completedWork == info.completedWork &&
//            infoToCheck.worker == info.worker &&
//            infoToCheck.workerStartPeriod == info.workerStartPeriod);
//
//        require(delegateGet(_testTarget, this.getPastDowntimeLength.selector, staker) ==
//            info.pastDowntime.length);
//        for (uint256 i = 0; i < info.pastDowntime.length && i < MAX_CHECKED_VALUES; i++) {
//            Downtime storage downtime = info.pastDowntime[i];
//            Downtime memory downtimeToCheck = delegateGetPastDowntime(_testTarget, staker, i);
//            require(downtimeToCheck.startPeriod == downtime.startPeriod &&
//                downtimeToCheck.endPeriod == downtime.endPeriod);
//        }
//
//        require(delegateGet(_testTarget, this.getSubStakesLength.selector, staker) == info.subStakes.length);
//        for (uint256 i = 0; i < info.subStakes.length && i < MAX_CHECKED_VALUES; i++) {
//            SubStakeInfo storage subStakeInfo = info.subStakes[i];
//            SubStakeInfo memory subStakeInfoToCheck = delegateGetSubStakeInfo(_testTarget, staker, i);
//            require(subStakeInfoToCheck.firstPeriod == subStakeInfo.firstPeriod &&
//                subStakeInfoToCheck.lastPeriod == subStakeInfo.lastPeriod &&
//                subStakeInfoToCheck.unlockingDuration == subStakeInfo.unlockingDuration &&
//                subStakeInfoToCheck.lockedValue == subStakeInfo.lockedValue);
//        }
//
//        // it's not perfect because checks not only slot value but also decoding
//        // at least without additional functions
//        require(delegateGet(_testTarget, this.totalStakedForAt.selector, staker, bytes32(block.number)) ==
//            totalStakedForAt(stakerAddress, block.number));
//        require(delegateGet(_testTarget, this.totalStakedAt.selector, bytes32(block.number)) ==
//            totalStakedAt(block.number));
//
//        if (info.worker != address(0)) {
//            require(address(delegateGet(_testTarget, this.stakerFromWorker.selector, bytes32(uint256(info.worker)))) ==
//                stakerFromWorker[info.worker]);
//        }
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `finishUpgrade`
    function finishUpgrade(address _target) public override virtual {
        super.finishUpgrade(_target);
        totalNUStaked = nuToken.balanceOf(address(this)) - (formerTotalNUSupply - totalNUSupply); // TODO ???

        // Create fake worker
        stakerFromWorker[address(0)] = address(this);
    }
}
