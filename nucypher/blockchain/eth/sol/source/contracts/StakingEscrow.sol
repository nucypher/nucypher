// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


import "aragon/interfaces/IERC900History.sol";
import "contracts/NuCypherToken.sol";
import "contracts/lib/Bits.sol";
import "contracts/lib/Snapshot.sol";
import "contracts/lib/AdditionalMath.sol";
import "contracts/proxy/Upgradeable.sol";
import "zeppelin/math/Math.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";


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

    /**
    * @notice Predefines some variables for use when deploying other contracts
    * @param _token Token contract
    */
    constructor(NuCypherToken _token) {
        require(_token.totalSupply() > 0);

        token = _token;
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
* @dev |v6.1.1|
*/
contract StakingEscrow is Upgradeable, IERC900History {

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
    * @notice Signals that the snapshot parameter was activated/deactivated
    * @param staker Staker address
    * @param snapshotsEnabled Updated parameter value
    */
    event SnapshotSet(address indexed staker, bool snapshotsEnabled);

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

    // indices for flags (0, 1, 2, and 4 were in use, skip it in future)
    uint8 internal constant SNAPSHOTS_DISABLED_INDEX = 3;

    NuCypherToken public immutable token;
    WorkLockInterface public immutable workLock;

    uint128 previousPeriodSupply; // outdated
    uint128 currentPeriodSupply; // outdated
    uint16 currentMintingPeriod; // outdated

    mapping (address => StakerInfo) public stakerInfo;
    address[] public stakers;
    mapping (address => address) stakerFromWorker;  // outdated

    mapping (uint16 => uint256) stub1; // former slot for lockedPerPeriod
    uint128[] public balanceHistory;

    address stub2; // former slot for PolicyManager
    address stub3; // former slot for Adjudicator
    address stub4; // former slot for WorkLock

    mapping (uint16 => uint256) public lockedPerPeriod; // outdated

    /**
    * @notice Constructor sets address of token contract and parameters for staking
    * @param _token NuCypher token contract
    * @param _workLock WorkLock contract. Zero address if there is no WorkLock
    */
    constructor(
        NuCypherToken _token,
        WorkLockInterface _workLock
    ) {
        require(_token.totalSupply() > 0 &&
            (address(_workLock) == address(0) || _workLock.token() == _token),
            "Input addresses must be deployed contracts"
        );

        token = _token;
        workLock = _workLock;
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
    * @notice Get all flags for the staker
    */
    function getFlags(address _staker)
        external view returns (
            bool snapshots
        )
    {
        StakerInfo storage info = stakerInfo[_staker];
        snapshots = !info.flags.bitSet(SNAPSHOTS_DISABLED_INDEX);
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
        stakers.push(_staker);
        token.safeTransferFrom(msg.sender, address(this), _value);
        info.value += _value;

        addSnapshot(info, int256(_value));
        emit Deposited(_staker, _value);
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
        bytes32 staker = bytes32(uint256(stakerAddress));
        StakerInfo memory infoToCheck = delegateGetStakerInfo(_testTarget, staker);
        require(
            infoToCheck.value == info.value &&
            infoToCheck.flags == info.flags
        );

        // it's not perfect because checks not only slot value but also decoding
        // at least without additional functions
        require(delegateGet(_testTarget, this.totalStakedForAt.selector, staker, bytes32(block.number)) ==
            totalStakedForAt(stakerAddress, block.number));
        require(delegateGet(_testTarget, this.totalStakedAt.selector, bytes32(block.number)) ==
            totalStakedAt(block.number));
    }

}
