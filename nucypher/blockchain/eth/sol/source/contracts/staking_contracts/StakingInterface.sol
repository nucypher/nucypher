pragma solidity ^0.5.3;


import "contracts/staking_contracts/AbstractStakingContract.sol";
import "contracts/NuCypherToken.sol";
import "contracts/StakingEscrow.sol";
import "contracts/PolicyManager.sol";
import "contracts/WorkLock.sol";


/**
* @notice Base StakingInterface
*/
contract BaseStakingInterface {

    NuCypherToken public token;
    StakingEscrow public escrow;
    PolicyManager public policyManager;
    WorkLock public workLock;

    /**
    * @notice Constructor sets addresses of the contracts
    * @param _token Token contract
    * @param _escrow Escrow contract
    * @param _policyManager PolicyManager contract
    * @param _workLock WorkLock contract
    */
    constructor(
        NuCypherToken _token,
        StakingEscrow _escrow,
        PolicyManager _policyManager,
        WorkLock _workLock
    )
        public
    {
        require(_token.totalSupply() > 0 &&
            _escrow.secondsPerPeriod() > 0 &&
            _policyManager.secondsPerPeriod() > 0 &&
            // in case there is no worklock contract
            (address(_workLock) == address(0) || _workLock.startBidDate() > 0));
        token = _token;
        escrow = _escrow;
        policyManager = _policyManager;
        workLock = _workLock;
    }

    /**
    * @notice Get contract which stores state
    * @dev Assume that `this` is the staking contract
    */
    function getStateContract() internal view returns (BaseStakingInterface) {
        address payable stakingContractAddress = address(bytes20(address(this)));
        StakingInterfaceRouter router = AbstractStakingContract(stakingContractAddress).router();
        return BaseStakingInterface(router.target());
    }

}


/**
* @notice Interface for accessing main contracts from a staking contract
* @dev All methods must be stateless because this code will be executed by delegatecall call.
* If state is needed - use getStateContract() method to access state of this contract.
* @dev |v1.4.1|
*/
contract StakingInterface is BaseStakingInterface {

    event DepositedAsStaker(address indexed sender, uint256 value, uint16 periods);
    event WithdrawnAsStaker(address indexed sender, uint256 value);
    event Locked(address indexed sender, uint256 value, uint16 periods);
    event Divided(address indexed sender, uint256 index, uint256 newValue, uint16 periods);
    event Mined(address indexed sender);
    event PolicyRewardWithdrawn(address indexed sender, uint256 value);
    event MinRewardRateSet(address indexed sender, uint256 value);
    event ReStakeSet(address indexed sender, bool reStake);
    event ReStakeLocked(address indexed sender, uint16 lockUntilPeriod);
    event WorkerSet(address indexed sender, address worker);
    event Prolonged(address indexed sender, uint256 index, uint16 periods);
    event WindDownSet(address indexed sender, bool windDown);
    event Bid(address indexed sender, uint256 depositedETH);
    event Claimed(address indexed sender, uint256 claimedTokens);
    event Refund(address indexed sender, uint256 refundETH);
    event BidCanceled(address indexed sender);
    event CompensationWithdrawn(address indexed sender);

    /**
    * @notice Constructor sets addresses of the contracts
    * @param _token Token contract
    * @param _escrow Escrow contract
    * @param _policyManager PolicyManager contract
    * @param _workLock WorkLock contract
    */
    constructor(
        NuCypherToken _token,
        StakingEscrow _escrow,
        PolicyManager _policyManager,
        WorkLock _workLock
    )
        public BaseStakingInterface(_token, _escrow, _policyManager, _workLock)
    {
    }

    /**
    * @notice Set `worker` parameter in the staking escrow
    * @param _worker Worker address
    */
    function setWorker(address _worker) public {
        getStateContract().escrow().setWorker(_worker);
        emit WorkerSet(msg.sender, _worker);
    }

    /**
    * @notice Set `reStake` parameter in the staking escrow
    * @param _reStake Value for parameter
    */
    function setReStake(bool _reStake) public {
        getStateContract().escrow().setReStake(_reStake);
        emit ReStakeSet(msg.sender, _reStake);
    }

    /**
    * @notice Lock `reStake` parameter in the staking escrow
    * @param _lockReStakeUntilPeriod Can't change `reStake` value until this period
    */
    function lockReStake(uint16 _lockReStakeUntilPeriod) public {
        getStateContract().escrow().lockReStake(_lockReStakeUntilPeriod);
        emit ReStakeLocked(msg.sender, _lockReStakeUntilPeriod);
    }

    /**
    * @notice Deposit tokens to the staking escrow
    * @param _value Amount of token to deposit
    * @param _periods Amount of periods during which tokens will be locked
    */
    function depositAsStaker(uint256 _value, uint16 _periods) public {
        BaseStakingInterface state = getStateContract();
        NuCypherToken tokenFromState = state.token();
        require(tokenFromState.balanceOf(address(this)) >= _value);
        StakingEscrow escrowFromState = state.escrow();
        tokenFromState.approve(address(escrowFromState), _value);
        escrowFromState.deposit(_value, _periods);
        emit DepositedAsStaker(msg.sender, _value, _periods);
    }

    /**
    * @notice Withdraw available amount of tokens from the staking escrow to the staking contract
    * @param _value Amount of token to withdraw
    */
    function withdrawAsStaker(uint256 _value) public {
        getStateContract().escrow().withdraw(_value);
        emit WithdrawnAsStaker(msg.sender, _value);
    }

    /**
    * @notice Lock some tokens or increase lock in the staking escrow
    * @param _value Amount of tokens which should lock
    * @param _periods Amount of periods during which tokens will be locked
    */
    function lock(uint256 _value, uint16 _periods) public {
        getStateContract().escrow().lock(_value, _periods);
        emit Locked(msg.sender, _value, _periods);
    }

    /**
    * @notice Divide stake into two parts
    * @param _index Index of stake
    * @param _newValue New stake value
    * @param _periods Amount of periods for extending stake
    */
    function divideStake(
        uint256 _index,
        uint256 _newValue,
        uint16 _periods
    )
        public
    {
        getStateContract().escrow().divideStake(_index, _newValue, _periods);
        emit Divided(msg.sender, _index, _newValue, _periods);
    }

    /**
    * @notice Mint tokens in the staking escrow
    */
    function mint() public {
        getStateContract().escrow().mint();
        emit Mined(msg.sender);
    }

    /**
    * @notice Withdraw available reward from the policy manager to the staking contract
    */
    function withdrawPolicyReward() public {
        uint256 value = getStateContract().policyManager().withdraw();
        emit PolicyRewardWithdrawn(msg.sender, value);
    }

    /**
    * @notice Set the minimum reward that the staker will take in the policy manager
    */
    function setMinRewardRate(uint256 _minRewardRate) public {
        getStateContract().policyManager().setMinRewardRate(_minRewardRate);
        emit MinRewardRateSet(msg.sender, _minRewardRate);
    }


    /**
    * @notice Prolong active sub stake
    * @param _index Index of the sub stake
    * @param _periods Amount of periods for extending sub stake
    */
    function prolongStake(uint256 _index, uint16 _periods) public {
        getStateContract().escrow().prolongStake(_index, _periods);
        emit Prolonged(msg.sender, _index, _periods);
    }

    /**
    * @notice Set `windDown` parameter in the staking escrow
    * @param _windDown Value for parameter
    */
    function setWindDown(bool _windDown) public {
        getStateContract().escrow().setWindDown(_windDown);
        emit WindDownSet(msg.sender, _windDown);
    }

    /**
    * @notice Bid for tokens by transferring ETH
    */
    function bid(uint256 _value) public payable {
        WorkLock workLockFromState = getStateContract().workLock();
        require(address(workLockFromState) != address(0));
        workLockFromState.bid.value(_value)();
        emit Bid(msg.sender, _value);
    }

    /**
    * @notice Cancel bid and refund deposited ETH
    */
    function cancelBid() public {
        WorkLock workLockFromState = getStateContract().workLock();
        require(address(workLockFromState) != address(0));
        workLockFromState.cancelBid();
        emit BidCanceled(msg.sender);
    }

    /**
    * @notice Withdraw compensation after force refund
    */
    function withdrawCompensation() public {
        WorkLock workLockFromState = getStateContract().workLock();
        require(address(workLockFromState) != address(0));
        workLockFromState.withdrawCompensation();
        emit CompensationWithdrawn(msg.sender);
    }

    /**
    * @notice Claimed tokens will be deposited and locked as stake in the StakingEscrow contract.
    */
    function claim() public {
        WorkLock workLockFromState = getStateContract().workLock();
        require(address(workLockFromState) != address(0));
        uint256 claimedTokens = workLockFromState.claim();
        emit Claimed(msg.sender, claimedTokens);
    }

    /**
    * @notice Refund ETH for the completed work
    */
    function refund() public {
        WorkLock workLockFromState = getStateContract().workLock();
        require(address(workLockFromState) != address(0));
        uint256 refundETH = workLockFromState.refund();
        emit Refund(msg.sender, refundETH);
    }

}
