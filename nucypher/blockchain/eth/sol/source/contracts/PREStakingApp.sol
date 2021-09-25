// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "zeppelin/math/Math.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";
import "zeppelin/token/ERC20/IERC20.sol";
import "contracts/threshold/IApplication.sol";
import "contracts/threshold/ITokenStaking.sol";
import "contracts/Adjudicator.sol";
import "contracts/PolicyManager.sol";


/**
* @title PRE Staking Application
* @notice Contract distributes rewards for participating in app and slashes for violating rules
*/
contract PREStakingApp is IApplication, Adjudicator, PolicyManager {

    using SafeERC20 for IERC20;

    // TODO docs
    event RewardAdded(uint256 reward);
    event RewardPaid(address indexed worker, uint256 reward);

    /**
    * @notice Signals that T tokens were withdrawn to the beneficiary
    * @param worker Worker address
    * @param beneficiary Beneficiary address
    * @param value Amount withdraws
    */
    event Withdrawn(address indexed worker, address indexed beneficiary, uint256 value);

    /**
    * @notice Signals that the worker was slashed
    * @param worker Worker address
    * @param penalty Slashing penalty
    * @param investigator Investigator address
    * @param reward Value of reward provided to investigator (in NuNits)
    */
    event Slashed(address indexed worker, uint256 penalty, address indexed investigator, uint256 reward);


    struct WorkerInfo {
        uint256 authorized;
        uint256 tReward;
        uint256 rewardPerTokenPaid;

        uint256 endDeauthorization;
        uint256 deauthorizing;
    }

    uint256 public immutable rewardDuration;
    uint256 public immutable deauthorizationDuration;
    uint256 public immutable override minAuthorizationSize;

    IERC20 public immutable token;
    ITokenStaking public immutable tokenStaking;

    mapping (address => WorkerInfo) public workerInfo;
    address[] public workers;

    uint256 public periodFinish = 0;
    uint256 public rewardRate = 0;
    uint256 public lastUpdateTime;
    uint256 public rewardPerTokenStored;
    uint256 public authorizedOverall;

    /**
    * @notice Constructor sets address of token contract and parameters for staking
    * @param _token T token contract
    * @param _tokenStaking T token staking contract
    * @param _rewardDuration Duration of one reward cycle
    */
    // TODO proper docs
    constructor(
        SignatureVerifier.HashAlgorithm _hashAlgorithm,
        uint256 _basePenalty,
        uint256 _penaltyHistoryCoefficient,
        uint256 _percentagePenaltyCoefficient,
        uint256 _rewardCoefficient,
        IERC20 _token,
        ITokenStaking _tokenStaking,
        uint256 _rewardDuration,
        uint256 _deauthorizationDuration,
        uint256 _minAuthorizationSize
    )
        Adjudicator(
            _hashAlgorithm,
            _basePenalty,
            _penaltyHistoryCoefficient,
            _percentagePenaltyCoefficient,
            _rewardCoefficient
        )
    {
        require(_rewardDuration != 0 &&
            _deauthorizationDuration != 0 &&
            _minAuthorizationSize != 0 &&
            _token.totalSupply() > 0);
        rewardDuration = _rewardDuration;
        deauthorizationDuration = _deauthorizationDuration;
        minAuthorizationSize = _minAuthorizationSize;
        token = _token;
        tokenStaking = _tokenStaking;
    }

    modifier updateReward(address _worker) {
        updateRewardInternal(_worker);
        _;
    }

    modifier onlyStakingContract()
    {
        require(msg.sender == address(tokenStaking));
        _;
    }

    //------------------------Reward------------------------------

    function updateRewardInternal(address _worker) internal {
        rewardPerTokenStored = rewardPerToken();
        lastUpdateTime = lastTimeRewardApplicable();
        if (_worker != address(0)) {
            WorkerInfo storage info = workerInfo[_worker];
            info.tReward = earned(_worker);
            info.rewardPerTokenPaid = rewardPerTokenStored;
        }

    }

    function lastTimeRewardApplicable() public view returns (uint256) {
        return Math.min(block.timestamp, periodFinish);
    }

    function rewardPerToken() public view returns (uint256) {
        if (authorizedOverall == 0) {
            return rewardPerTokenStored;
        }
        return
            rewardPerTokenStored +
                (lastTimeRewardApplicable() - lastUpdateTime)
                * rewardRate
                * 1e18
                / authorizedOverall;
    }

    function earned(address _worker) public view returns (uint256) {
        WorkerInfo storage info = workerInfo[_worker];
        return info.authorized * (rewardPerToken() - info.rewardPerTokenPaid) / 1e18 + info.tReward;
    }

    function withdrawReward() public updateReward(msg.sender) {
        uint256 reward = earned(msg.sender);
        if (reward > 0) {
            workerInfo[msg.sender].tReward = 0;
            token.safeTransfer(msg.sender, reward);
            emit RewardPaid(msg.sender, reward);
        }
    }

    function pushReward(uint256 _reward) external updateReward(address(0)) {
        require(_reward > 0);
        token.safeTransfer(msg.sender, _reward);
        if (block.timestamp >= periodFinish) {
            rewardRate = _reward / rewardDuration;
        } else {
            uint256 remaining = periodFinish - block.timestamp;
            uint256 leftover = remaining * rewardRate;
            rewardRate = (_reward + leftover) / rewardDuration;
        }
        lastUpdateTime = block.timestamp;
        periodFinish = block.timestamp + rewardDuration;
        emit RewardAdded(_reward);
    }

    /**
    * @notice Withdraw available amount of T reward to worker
    * @param _value Amount of tokens to withdraw
    */
    function withdraw(address _worker, uint256 _value) external updateReward(_worker) {
        WorkerInfo storage info = workerInfo[_worker];
        require(_value <= info.tReward);
        info.tReward -= _value;
        address beneficiary = tokenStaking.beneficiaryOf(_worker);
        emit Withdrawn(_worker, beneficiary, _value);
        token.safeTransfer(beneficiary, _value);
    }

    /**
    * @notice Recalculate reward and store authorization
    * @param _worker Address of worker
    * @param _amount Amount of authorized tokens to PRE application by worker
    */
    function authorizationIncreased(address _worker, uint256 _amount) external override onlyStakingContract {
        require(_worker != address(0));

        WorkerInfo storage info = workerInfo[_worker];
        if (info.rewardPerTokenPaid == 0) {
            workers.push(_worker);
        }

        updateRewardInternal(_worker);

        info.authorized += _amount;
        authorizedOverall += _amount;
        // TODO emit event
    }

    // TODO docs
    function involuntaryAllocationDecrease(address _worker, uint256 _amount)
        external override onlyStakingContract updateReward(_worker)
    {
        WorkerInfo storage info = workerInfo[_worker];
        info.authorized -= _amount;
        authorizedOverall -= _amount;
        // TODO emit event
    }

    // TODO docs
    function authorizationDecreaseRequested(address _worker, uint256 _amount)
        external override onlyStakingContract
    {
        WorkerInfo storage info = workerInfo[_worker];
        require(_amount <= info.authorized);
        info.deauthorizing = _amount;
        info.endDeauthorization = block.timestamp + deauthorizationDuration;
        // TODO emit event
    }

    // TODO docs
    // TODO who can call this? same as in request?
    function finishDeauthorization() external updateReward(msg.sender) {
        WorkerInfo storage info = workerInfo[msg.sender];
        require(info.endDeauthorization >= block.timestamp);

        info.authorized -= info.deauthorizing;
        authorizedOverall -= info.deauthorizing;
        info.deauthorizing = 0;
        info.endDeauthorization = 0;

        // TODO emit event
        tokenStaking.approveAuthorizationDecrease(msg.sender);
    }

    //-------------------------Main-------------------------
    /**
    * @notice Get all tokens authorized to the worker
    */
    function getAllTokens(address _worker) public override view returns (uint256) { // TODO rename
        return workerInfo[_worker].authorized;
    }

    /**
    * @notice Get the value of authorized tokens for active workers as well as workers and their authorized tokens
    * @param _startIndex Start index for looking in workers array
    * @param _maxWorkers Max workers for looking, if set 0 then all will be used
    * @return allAuthorizedTokens Sum of authorized tokens for active workers
    * @return activeWorkers Array of workers and their authorized tokens. Workers addresses stored as uint256
    * @dev Note that activeWorkers[0] in an array of uint256, but you want addresses. Careful when used directly!
    */
    function getActiveWorkers(uint256 _startIndex, uint256 _maxWorkers)
        external view returns (uint256 allAuthorizedTokens, uint256[2][] memory activeWorkers)
    {
        uint256 endIndex = workers.length;
        require(_startIndex < endIndex);
        if (_maxWorkers != 0 && _startIndex + _maxWorkers < endIndex) {
            endIndex = _startIndex + _maxWorkers;
        }
        activeWorkers = new uint256[2][](endIndex - _startIndex);
        allAuthorizedTokens = 0;

        uint256 resultIndex = 0;
        for (uint256 i = _startIndex; i < endIndex; i++) {
            address worker = workers[i];
            WorkerInfo storage info = workerInfo[worker];
            uint256 eligibleAmount = info.authorized - info.deauthorizing;
            if (eligibleAmount == 0) {
                continue;
            }
            activeWorkers[resultIndex][0] = uint256(uint160(worker));
            activeWorkers[resultIndex++][1] = eligibleAmount;
            allAuthorizedTokens += eligibleAmount;
        }
        assembly {
            mstore(activeWorkers, resultIndex)
        }
    }

    // TODO docs
    function getBeneficiary(address _worker) internal override view returns (address payable) {
        return tokenStaking.beneficiaryOf(_worker);
    }

    // TODO docs
    function isAuthorized(address _worker) internal override view returns (bool) {
        return workerInfo[_worker].authorized > 0;
    }

    //-------------------------Slashing-------------------------
    /**
    * @notice Slash the worker's stake and reward the investigator
    * @param _worker Worker's address
    * @param _penalty Penalty
    * @param _investigator Investigator
    * @param _reward Reward for the investigator
    */
    function slash(
        address _worker,
        uint256 _penalty,
        address _investigator,
        uint256 _reward
    )
        internal override updateReward(_worker)
    {
        // TODO
    }

}
