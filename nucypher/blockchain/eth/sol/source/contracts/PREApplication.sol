// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "zeppelin/math/Math.sol";
import "zeppelin/math/SafeCast.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";
import "zeppelin/token/ERC20/IERC20.sol";
import "contracts/threshold/IApplication.sol";
import "contracts/threshold/ITokenStaking.sol";
import "contracts/Adjudicator.sol";
import "contracts/PolicyManager.sol";


/**
* @title PRE Application
* @notice Contract distributes rewards for participating in app and slashes for violating rules
*/
contract PREApplication is IApplication, Adjudicator, PolicyManager {

    using SafeERC20 for IERC20;
    using SafeCast for uint256;

    /**
    * @notice Signals that reward was added
    * @param reward Amount of reward
    */
    event RewardAdded(uint256 reward);

    /**
    * @notice Signals that the beneficiary related to the operator received reward
    * @param operator Operator address
    * @param beneficiary Beneficiary address
    * @param reward Amount of reward
    */
    event RewardPaid(address indexed operator, address indexed beneficiary, uint256 reward);

    /**
    * @notice Signals that authorization was increased for the operator
    * @param operator Operator address
    * @param amount Amount of increased authorization
    */
    event AuthorizationIncreased(address indexed operator, uint96 amount);

    /**
    * @notice Signals that authorization was decreased involuntary
    * @param operator Operator address
    * @param amount Amount of decreased authorization
    */
    event AuthorizationInvoluntaryDecreased(address indexed operator, uint96 amount);

    /**
    * @notice Signals that authorization decrease was requested for the operator
    * @param operator Operator address
    * @param amount Amount of authorization to decrease
    */
    event AuthorizationDecreaseRequested(address indexed operator, uint96 amount);

    /**
    * @notice Signals that authorization decrease was approved for the operator
    * @param operator Operator address
    * @param amount Amount of decreased authorization
    */
    event AuthorizationDecreaseApproved(address indexed operator, uint96 amount);

    /**
    * @notice Signals that authorization was resynchronized
    * @param operator Operator address
    */
    event AuthorizationReSynchronized(address indexed operator);

    /**
    * @notice Signals that the operator was slashed
    * @param operator Operator address
    * @param penalty Slashing penalty
    * @param investigator Investigator address
    * @param reward Value of reward provided to investigator (in NuNits)
    */
    event Slashed(address indexed operator, uint256 penalty, address indexed investigator, uint256 reward);

    struct OperatorInfo {
        uint96 authorized;
        uint96 tReward;
        uint96 rewardPerTokenPaid;

        uint96 deauthorizing;
        uint256 endDeauthorization;
    }

    uint256 public immutable rewardDuration;
    uint256 public immutable deauthorizationDuration;
    uint256 public immutable minAuthorization;

    IERC20 public immutable token;
    ITokenStaking public immutable tokenStaking;

    mapping (address => OperatorInfo) public operatorInfo;
    address[] public operators;

    address public rewardDistributor;
    uint256 public periodFinish = 0;
    uint96 public rewardRate = 0;
    uint256 public lastUpdateTime;
    uint96 public rewardPerTokenStored;
    uint96 public authorizedOverall;

    /**
    * @notice Constructor sets address of token contract and parameters for staking
    * @param _hashAlgorithm Hashing algorithm
    * @param _basePenalty Base for the penalty calculation
    * @param _penaltyHistoryCoefficient Coefficient for calculating the penalty depending on the history
    * @param _percentagePenaltyCoefficient Coefficient for calculating the percentage penalty
    * @param _token T token contract
    * @param _tokenStaking T token staking contract
    * @param _rewardDuration Duration of one reward cycle
    * @param _deauthorizationDuration Duration of decreasing authorization
    * @param _minAuthorization Amount of minimum allowable authorization
    *
    */
    constructor(
        SignatureVerifier.HashAlgorithm _hashAlgorithm,
        uint256 _basePenalty,
        uint256 _penaltyHistoryCoefficient,
        uint256 _percentagePenaltyCoefficient,
        IERC20 _token,
        ITokenStaking _tokenStaking,
        uint256 _rewardDuration,
        uint256 _deauthorizationDuration,
        uint256 _minAuthorization
    )
        Adjudicator(
            _hashAlgorithm,
            _basePenalty,
            _penaltyHistoryCoefficient,
            _percentagePenaltyCoefficient
        )
    {
        require(
            _rewardDuration != 0 &&
            _token.totalSupply() > 0,
            "Wrong input parameters"
        );
        rewardDuration = _rewardDuration;
        deauthorizationDuration = _deauthorizationDuration;
        minAuthorization = _minAuthorization;
        token = _token;
        tokenStaking = _tokenStaking;
    }

    /**
    * @dev Update reward for the specified operator
    */
    modifier updateReward(address _operator) {
        updateRewardInternal(_operator);
        _;
    }

    /**
    * @dev Checks caller is T staking contract
    */
    modifier onlyStakingContract()
    {
        require(msg.sender == address(tokenStaking), "Caller must be the T staking contract");
        _;
    }

    //------------------------Reward------------------------------

    /**
    * @notice Set reward distributor address
    */
    function setRewardDistributor(address _rewardDistributor)
        external
        onlyOwner
    {
        rewardDistributor = _rewardDistributor;
    }

    /**
    * @notice Update reward for the specified operator
    * @param _operator Operator address
    */
    function updateRewardInternal(address _operator) internal {
        rewardPerTokenStored = rewardPerToken();
        lastUpdateTime = lastTimeRewardApplicable();
        if (_operator != address(0)) {
            OperatorInfo storage info = operatorInfo[_operator];
            info.tReward = earned(_operator);
            info.rewardPerTokenPaid = rewardPerTokenStored;
        }
    }

    /**
    * @notice Returns last time when reward was applicable
    */
    function lastTimeRewardApplicable() public view returns (uint256) {
        return Math.min(block.timestamp, periodFinish);
    }

    /**
    * @notice Returns current value of reward per token
    */
    function rewardPerToken() public view returns (uint96) {
        if (authorizedOverall == 0) {
            return rewardPerTokenStored;
        }
        uint256 result = rewardPerTokenStored +
                (lastTimeRewardApplicable() - lastUpdateTime)
                * rewardRate
                * 1e18
                / authorizedOverall;
        return result.toUint96();
    }

    /**
    * @notice Returns amount of reward for the operator
    * @param _operator Operator address
    */
    function earned(address _operator) public view returns (uint96) {
        OperatorInfo storage info = operatorInfo[_operator];
        return info.authorized * (rewardPerToken() - info.rewardPerTokenPaid) / 1e18 + info.tReward;
    }

    /**
    * @notice Transfer reward for the next period. Can be called only by distributor
    * @param _reward Amount of reward
    */
    function pushReward(uint96 _reward) external updateReward(address(0)) {
        require(msg.sender == rewardDistributor, "Only distributor can transfer reward");
        require(_reward > 0, "Reward must be specified");
        if (block.timestamp >= periodFinish) {
            rewardRate = (_reward / rewardDuration).toUint96();
        } else {
            uint256 remaining = periodFinish - block.timestamp;
            uint256 leftover = remaining * rewardRate;
            rewardRate = ((_reward + leftover) / rewardDuration).toUint96();
        }
        lastUpdateTime = block.timestamp;
        periodFinish = block.timestamp + rewardDuration;
        emit RewardAdded(_reward);
        token.safeTransfer(msg.sender, _reward);
    }

    /**
    * @notice Withdraw available amount of T reward to beneficiary. Can be called only by beneficiary
    * @param _operator Operator address
    */
    function withdraw(address _operator) external updateReward(_operator) {
        address beneficiary = tokenStaking.beneficiaryOf(_operator);
        require(msg.sender == beneficiary, "Caller must be beneficiary");

        OperatorInfo storage info = operatorInfo[_operator];
        require(info.tReward > 0, "No reward to withdraw");
        uint96 value = info.tReward;
        info.tReward = 0;
        emit RewardPaid(_operator, beneficiary, value);
        token.safeTransfer(beneficiary, value);
    }

    //------------------------Authorization------------------------------

    /**
    * @notice Recalculate reward and save increased authorization. Can be called only by staking contract
    * @param _operator Address of operator
    * @param _amount Amount of authorized tokens to PRE application by operator
    */
    function authorizationIncreased(address _operator, uint96 _amount) external override onlyStakingContract {
        require(_operator != address(0) && _amount > 0, "Input parameters must be specified");

        OperatorInfo storage info = operatorInfo[_operator];
        if (info.rewardPerTokenPaid == 0) {
            operators.push(_operator);
        }

        updateRewardInternal(_operator);

        info.authorized += _amount;
        require(info.authorized >= minAuthorization, "Authorization must be greater than minimum");
        authorizedOverall += _amount;
        emit AuthorizationIncreased(_operator, _amount);
    }

    /**
    * @notice Immediately decrease authorization. Can be called only by staking contract
    * @param _operator Address of operator
    * @param _amount Amount of authorized tokens to decrease
    */
    function involuntaryAuthorizationDecrease(address _operator, uint96 _amount)
        external override onlyStakingContract updateReward(_operator)
    {
        OperatorInfo storage info = operatorInfo[_operator];
        info.authorized -= _amount;
        if (info.authorized < info.deauthorizing) {
            info.deauthorizing = info.authorized;
        }
        authorizedOverall -= _amount;
        emit AuthorizationInvoluntaryDecreased(_operator, _amount);
    }

    /**
    * @notice Register request of decreasing authorization. Can be called only by staking contract
    * @param _operator Address of operator
    * @param _amount Amount of authorized tokens to decrease
    */
    function authorizationDecreaseRequested(address _operator, uint96 _amount)
        external override onlyStakingContract
    {
        OperatorInfo storage info = operatorInfo[_operator];
        require(_amount <= info.authorized, "Amount to decrease greater than authorized");
        require(
            info.authorized - _amount >= minAuthorization,
            "Resulting authorization will be less than minimum"
        );
        info.deauthorizing = _amount;
        info.endDeauthorization = block.timestamp + deauthorizationDuration;
        emit AuthorizationDecreaseRequested(_operator, _amount);
    }

    /**
    * @notice Approve request of decreasing authorization. Can be called only by anyone
    * @param _operator Address of operator
    */
    function finishAuthorizationDecrease(address _operator) external updateReward(_operator) {
        OperatorInfo storage info = operatorInfo[_operator];
        require(info.deauthorizing > 0, "There is no deauthorizing in process");
        require(info.endDeauthorization >= block.timestamp, "Authorization decrease has not finished yet");

        emit AuthorizationDecreaseApproved(_operator, info.deauthorizing);
        info.authorized -= info.deauthorizing;
        authorizedOverall -= info.deauthorizing;
        info.deauthorizing = 0;
        info.endDeauthorization = 0;

        tokenStaking.approveAuthorizationDecrease(_operator);
    }

    /**
    * @notice Read authorization from staking contract and store it. Can be called only by anyone
    * @param _operator Address of operator
    */
    function resynchronizeAuthorization(address _operator) external {
        OperatorInfo storage info = operatorInfo[_operator];
        uint96 authorized = tokenStaking.authorizedStake(_operator, address(this));
        require(info.authorized != authorized, "Nothing to synchronize");
        authorizedOverall -= authorized - info.authorized;
        info.authorized = authorized;
        if (info.authorized < info.deauthorizing) {
            info.deauthorizing = info.authorized; // TODO ideally resync this too
        }
        emit AuthorizationReSynchronized(_operator);
    }

    //-------------------------Main-------------------------
    /**
    * @notice Get all tokens delegated to the operator
    */
    function authorizedStake(address _operator) public override view returns (uint96) {
        return operatorInfo[_operator].authorized;
    }

    /**
    * @notice Get the value of authorized tokens for active operators as well as operators and their authorized tokens
    * @param _startIndex Start index for looking in operators array
    * @param _maxOperators Max operators for looking, if set 0 then all will be used
    * @return allAuthorizedTokens Sum of authorized tokens for active operators
    * @return activeOperators Array of operators and their authorized tokens. Operators addresses stored as uint256
    * @dev Note that activeOperators[0] in an array of uint256, but you want addresses. Careful when used directly!
    */
    function getActiveOperators(uint256 _startIndex, uint256 _maxOperators)
        external view returns (uint256 allAuthorizedTokens, uint256[2][] memory activeOperators)
    {
        uint256 endIndex = operators.length;
        require(_startIndex < endIndex, "Wrong start index");
        if (_maxOperators != 0 && _startIndex + _maxOperators < endIndex) {
            endIndex = _startIndex + _maxOperators;
        }
        activeOperators = new uint256[2][](endIndex - _startIndex);
        allAuthorizedTokens = 0;

        uint256 resultIndex = 0;
        for (uint256 i = _startIndex; i < endIndex; i++) {
            address operator = operators[i];
            OperatorInfo storage info = operatorInfo[operator];
            uint256 eligibleAmount = info.authorized - info.deauthorizing;
            if (eligibleAmount == 0) {
                continue;
            }
            activeOperators[resultIndex][0] = uint256(uint160(operator));
            activeOperators[resultIndex++][1] = eligibleAmount;
            allAuthorizedTokens += eligibleAmount;
        }
        assembly {
            mstore(activeOperators, resultIndex)
        }
    }

    /**
    * @notice Returns beneficiary related to the operator
    */
    function getBeneficiary(address _operator) internal override view returns (address payable) {
        return tokenStaking.beneficiaryOf(_operator);
    }

    /**
    * @notice Returns true if operator has authorized stake to this application
    */
    function isAuthorized(address _operator) internal override view returns (bool) {
        return operatorInfo[_operator].authorized > 0;
    }

    //-------------------------Slashing-------------------------
    /**
    * @notice Slash the operator's stake and reward the investigator
    * @param _operator Operator's address
    * @param _penalty Penalty
    * @param _investigator Investigator
    */
    function slash(
        address _operator,
        uint96 _penalty,
        address _investigator
    )
        internal override
    {
        address[] memory operatorWrapper = new address[](1);
        operatorWrapper[0] = _operator;
        tokenStaking.seize(_penalty, 100, _investigator, operatorWrapper);
    }

}
