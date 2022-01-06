// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "aragon/interfaces/IERC900History.sol";
import "contracts/NuCypherToken.sol";
import "contracts/lib/Bits.sol";
import "contracts/proxy/Upgradeable.sol";
import "zeppelin/math/Math.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";
import "threshold/IStaking.sol";


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
    // only to deploy WorkLock
    uint32 public immutable secondsPerPeriod = 1;
    uint16 public immutable minLockedPeriods = 0;
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
        require(address(uint160(delegateGet(_testTarget, this.token.selector))) == address(token));
    }
}


/**
* @title StakingEscrow
* @notice Contract holds and locks stakers tokens.
* Each staker that locks their tokens will receive some compensation
* @dev |v6.2.1|
*/
contract StakingEscrow is Upgradeable, IERC900History {

    using Bits for uint256;
    using SafeERC20 for NuCypherToken;

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
    event Withdrawn(address indexed staker, uint256 value);

    /**
    * @notice Signals that the staker was slashed
    * @param staker Staker address
    * @param penalty Slashing penalty
    * @param investigator Investigator address
    * @param reward Value of reward provided to investigator (in NuNits)
    */
    event Slashed(address indexed staker, uint256 penalty, address indexed investigator, uint256 reward);

    /**
    * @notice Signals that vesting parameters were set for the staker
    * @param staker Staker address
    * @param releaseTimestamp Release timestamp
    * @param releaseRate Release rate
    */
    event VestingSet(address indexed staker, uint256 releaseTimestamp, uint256 releaseRate);

    /**
    * @notice Signals that the staker requested merge with T staking contract
    * @param staker Staker address
    * @param operator Operator address
    */
    event MergeRequested(address indexed staker, address indexed operator);

    struct StakerInfo {
        uint256 value;

        uint16 stub1; // former slot for currentCommittedPeriod // TODO combine slots?
        uint16 stub2; // former slot for nextCommittedPeriod
        uint16 lastCommittedPeriod; // used only in depositFromWorkLock
        uint16 stub4; // former slot for lockReStakeUntilPeriod
        uint256 stub5; // former slot for completedWork
        uint16 stub6; // former slot for workerStartPeriod
        address stub7; // former slot for worker

        uint256 flags; // uint256 to acquire whole slot and minimize operations on it

        uint256 vestingReleaseTimestamp;
        uint256 vestingReleaseRate;
        address operator;

        uint256 reservedSlot4;
        uint256 reservedSlot5;

        uint256[] stub8; // former slot for pastDowntime
        uint256[] stub9; // former slot for subStakes
        uint128[] stub10; // former slot for history

    }

    // indices for flags (0-4 were in use, skip it in future)
//    uint8 internal constant SOME_FLAG_INDEX = 5;

    NuCypherToken public immutable token;
    WorkLockInterface public immutable workLock;
    IStaking public immutable tStaking;

    uint128 private stub1; // former slot for previousPeriodSupply
    uint128 public currentPeriodSupply; // resulting token supply
    uint16 private stub2; // former slot for currentMintingPeriod

    mapping (address => StakerInfo) public stakerInfo;
    address[] public stakers;
    mapping (address => address) private stub3; // former slot for stakerFromWorker

    mapping (uint16 => uint256) private stub4; // former slot for lockedPerPeriod
    uint128[] private stub5;  // former slot for balanceHistory

    address private stub6; // former slot for PolicyManager
    address private stub7; // former slot for Adjudicator
    address private stub8; // former slot for WorkLock

    mapping (uint16 => uint256) private stub9; // last former slot for lockedPerPeriod

    /**
    * @notice Constructor sets address of token contract and parameters for staking
    * @param _token NuCypher token contract
    * @param _workLock WorkLock contract. Zero address if there is no WorkLock
    * @param _tStaking T token staking contract
    */
    constructor(
        NuCypherToken _token,
        WorkLockInterface _workLock,
        IStaking _tStaking
    ) {
        require(_token.totalSupply() > 0 &&
            _tStaking.stakedNu(address(0)) == 0 &&
            (address(_workLock) == address(0) || _workLock.token() == _token),
            "Input addresses must be deployed contracts"
        );

        token = _token;
        workLock = _workLock;
        tStaking = _tStaking;
    }

    /**
    * @dev Checks the existence of a staker in the contract
    */
    modifier onlyStaker()
    {
        require(stakerInfo[msg.sender].value > 0, "Caller must be a staker");
        _;
    }

    /**
    * @dev Checks caller is T staking contract
    */
    modifier onlyTStakingContract()
    {
        require(msg.sender == address(tStaking), "Caller must be the T staking contract");
        _;
    }

    /**
    * @dev Checks caller is WorkLock contract
    */
    modifier onlyWorkLock()
    {
        require(msg.sender == address(workLock), "Caller must be the WorkLock contract");
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
    * @notice Get work that completed by the staker
    */
    function getCompletedWork(address _staker) external view returns (uint256) {
        return token.totalSupply();
    }


    //------------------------Main methods------------------------
    /**
    * @notice Stub for WorkLock
    * @param _staker Staker
    * @param _measureWork Value for `measureWork` parameter
    * @return Work that was previously done
    */
    function setWorkMeasurement(address _staker, bool _measureWork)
        external onlyWorkLock returns (uint256)
    {
        return 0;
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
        external onlyWorkLock
    {
        require(_value != 0, "Amount of tokens to deposit must be specified");
        StakerInfo storage info = stakerInfo[_staker];
        // initial stake of the staker
        if (info.value == 0 && info.lastCommittedPeriod == 0) {
            stakers.push(_staker);
        }
        token.safeTransferFrom(msg.sender, address(this), _value);
        info.value += _value;

        emit Deposited(_staker, _value);
    }

    /**
    * @notice Withdraw available amount of NU tokens to staker
    * @param _value Amount of tokens to withdraw
    */
    function withdraw(uint256 _value) external onlyStaker {
        require(_value > 0, "Value must be specified");
        StakerInfo storage info = stakerInfo[msg.sender];
        require(
            _value + tStaking.stakedNu(info.operator) <= info.value,
            "Not enough tokens unstaked in T staking contract"
        );
        require(
            _value + getUnvestedTokens(msg.sender) <= info.value,
            "Not enough tokens released during vesting"
        );
        info.value -= _value;

        token.safeTransfer(msg.sender, _value);
        emit Withdrawn(msg.sender, _value);
    }

    /**
    * @notice Returns amount of not released yet tokens for staker
    */
    function getUnvestedTokens(address _staker) public view returns (uint256) {
        StakerInfo storage info = stakerInfo[_staker];
        if (info.vestingReleaseTimestamp <= block.timestamp) {
            return 0;
        }
        if (info.vestingReleaseRate == 0) {
            // this value includes all not withdrawn reward
            return info.value;
        }
        uint256 unvestedTokens = (info.vestingReleaseTimestamp - block.timestamp) * info.vestingReleaseRate;
        return info.value < unvestedTokens ? info.value : unvestedTokens;
    }

    /**
    * @notice Setup vesting parameters
    * @param _stakers Array of stakers
    * @param _releaseTimestamp Array of timestamps when stake will be released
    * @param _releaseRate Array of release rates
    * @dev If release rate is 0 then all value will be locked before release timestamp
    */
    function setupVesting(
        address[] calldata _stakers,
        uint256[] calldata _releaseTimestamp,
        uint256[] calldata _releaseRate
    ) external onlyOwner {
        require(_stakers.length == _releaseTimestamp.length &&
            _releaseTimestamp.length == _releaseRate.length,
            "Input arrays must have same number of elements"
        );
        for (uint256 i = 0; i < _stakers.length; i++) {
            address staker = _stakers[i];
            StakerInfo storage info = stakerInfo[staker];
            require(info.vestingReleaseTimestamp == 0, "Vesting parameters can be set only once");
            info.vestingReleaseTimestamp = _releaseTimestamp[i];
            info.vestingReleaseRate = _releaseRate[i];
            require(getUnvestedTokens(staker) > 0, "Vesting parameters must be set properly");
            emit VestingSet(staker, info.vestingReleaseTimestamp, info.vestingReleaseRate);
        }
    }

    /**
    * @notice Request migration to threshold network
    * @param _staker Staker address
    * @param _operator Operator address
    * @return Amount of tokens
    */
    function requestMerge(address _staker, address _operator)
        external onlyTStakingContract returns (uint256)
    {
        StakerInfo storage info = stakerInfo[_staker];
        require(
            info.operator == address(0) ||
            info.operator == _operator ||
            tStaking.stakedNu(info.operator) == 0,
            "Operator already set for the staker"
        );
        if (info.operator != _operator) {
            info.operator = _operator;
            emit MergeRequested(_staker, _operator);
        }
        return info.value;
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
        external onlyTStakingContract
    {
        require(_penalty > 0, "Penalty must be specified");
        StakerInfo storage info = stakerInfo[_staker];
        if (info.value <= _penalty) {
            _penalty = info.value;
        }
        info.value -= _penalty;
        if (_reward > _penalty) {
            _reward = _penalty;
        }

        emit Slashed(_staker, _penalty, _investigator, _reward);
        if (_reward > 0) {
            token.safeTransfer(_investigator, _reward);
        }
    }

    //-------------Additional getters for stakers info-------------
    /**
    * @notice Return the length of the array of stakers
    */
    function getStakersLength() external view virtual returns (uint256) {
        return stakers.length;
    }

    //------------------ ERC900 connectors ----------------------

    function totalStakedForAt(address _owner, uint256 _blockNumber) public view override returns (uint256) {
        return 0;
    }

    function totalStakedAt(uint256 _blockNumber) public view override returns (uint256) {
        return token.totalSupply();
    }

    function supportsHistory() external pure override returns (bool) {
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

        require(delegateGet(_testTarget, this.getStakersLength.selector) == stakers.length);
        if (stakers.length == 0) {
            return;
        }
        address stakerAddress = stakers[0];
        require(address(uint160(delegateGet(_testTarget, this.stakers.selector, 0))) == stakerAddress);
        StakerInfo storage info = stakerInfo[stakerAddress];
        bytes32 staker = bytes32(uint256(uint160(stakerAddress)));
        StakerInfo memory infoToCheck = delegateGetStakerInfo(_testTarget, staker);
        require(infoToCheck.value == info.value &&
            infoToCheck.vestingReleaseTimestamp == info.vestingReleaseTimestamp &&
            infoToCheck.vestingReleaseRate == info.vestingReleaseRate &&
            infoToCheck.operator == info.operator &&
            infoToCheck.flags == info.flags
        );
    }

}
