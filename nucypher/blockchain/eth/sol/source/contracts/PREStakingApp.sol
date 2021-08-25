// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "zeppelin/math/Math.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";
import "zeppelin/token/ERC20/IERC20.sol";
import "contracts/threshold/IApplication.sol";
import "contracts/threshold/ITokenStaking.sol";


/**
* @title PRE Staking Application
* @notice Contract distributes rewards for participating in app and slashes for violating rules
*/
contract PREStakingApp is IApplication {

    using SafeERC20 for IERC20;

    // TODO docs
    event RewardAdded(uint256 reward);
    event RewardPaid(address indexed staker, uint256 reward);

    /**
    * @notice Signals that T tokens were withdrawn to the staker
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


    struct RewardInfo {
        uint256 allocated;
        uint256 tReward;
        uint256 rewardPerTokenPaid;
    }

    uint256 public immutable rewardDuration;

    IERC20 public immutable token;
    ITokenStaking public immutable tokenStaking;

    mapping (address => RewardInfo) public rewardInfo;

    uint256 public periodFinish = 0;
    uint256 public rewardRate = 0;
    uint256 public lastUpdateTime;
    uint256 public rewardPerTokenStored;
    uint256 public allocatedOverall;

    /**
    * @notice Constructor sets address of token contract and parameters for staking
    * @param _token T token contract
    * @param _tokenStaking T token staking contract
    * @param _rewardDuration Duration of one reward cycle
    */
    constructor(IERC20 _token, ITokenStaking _tokenStaking, uint256 _rewardDuration) {
        require(_rewardDuration != 0 &&
            _token.totalSupply() > 0);
        rewardDuration = _rewardDuration;
        token = _token;
        tokenStaking = _tokenStaking;
    }

    modifier updateReward(address _staker) {
        rewardPerTokenStored = rewardPerToken();
        lastUpdateTime = lastTimeRewardApplicable();
        if (_staker != address(0)) {
            RewardInfo storage info = rewardInfo[_staker];
            info.tReward = earned(_staker);
            info.rewardPerTokenPaid = rewardPerTokenStored;
        }
        _;
    }

    //------------------------Reward------------------------------

    function lastTimeRewardApplicable() public view returns (uint256) {
        return Math.min(block.timestamp, periodFinish);
    }

    function rewardPerToken() public view returns (uint256) {
        if (allocatedOverall == 0) {
            return rewardPerTokenStored;
        }
        return
            rewardPerTokenStored +
                (lastTimeRewardApplicable() - lastUpdateTime)
                * rewardRate
                * 1e18
                / allocatedOverall;
    }

    function earned(address _staker) public view returns (uint256) {
        RewardInfo storage info = rewardInfo[_staker];
        return info.allocated * (rewardPerToken() - info.rewardPerTokenPaid) / 1e18 + info.tReward;
    }

    function withdrawReward() public updateReward(msg.sender) {
        uint256 reward = earned(msg.sender);
        if (reward > 0) {
            rewardInfo[msg.sender].tReward = 0;
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
    * @notice Withdraw available amount of T reward to staker
    * @param _value Amount of tokens to withdraw
    */
    function withdraw(uint256 _value) external updateReward(msg.sender) {
        RewardInfo storage info = rewardInfo[msg.sender];
        require(_value <= info.tReward);
        info.tReward -= _value;
        emit Withdrawn(msg.sender, _value);
    }

    /**
    * @notice Recalculate reward and store allocation
    * @param _staker Address of staker
    * @param _allocated Amount of allocated tokens to PRE application by staker
    * @param _allocationPerApp Amount of allocated tokens to PRE application by all stakers
    */
    function receiveAllocation(address _staker, uint256 _allocated, uint256 _allocationPerApp)
        external override updateReward(_staker)
    {
        require(msg.sender == address(tokenStaking));
        require(_staker != address(0));

        rewardInfo[_staker].allocated = _allocated;
        allocatedOverall = _allocationPerApp;
        // TODO emit event
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
    }

}
