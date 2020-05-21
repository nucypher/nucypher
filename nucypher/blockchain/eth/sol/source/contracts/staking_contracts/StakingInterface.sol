pragma solidity ^0.6.5;


import "contracts/staking_contracts/AbstractStakingContract.sol";
import "contracts/NuCypherToken.sol";
import "contracts/StakingEscrow.sol";
import "contracts/PolicyManager.sol";
import "contracts/WorkLock.sol";


/**
* @notice Base StakingInterface
*/
contract BaseStakingInterface {

    address public immutable stakingInterfaceAddress;
    NuCypherToken public immutable token;
    StakingEscrow public immutable escrow;
    PolicyManager public immutable policyManager;
    WorkLock public immutable workLock;

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
            (address(_workLock) == address(0) || _workLock.boostingRefund() > 0));
        token = _token;
        escrow = _escrow;
        policyManager = _policyManager;
        workLock = _workLock;
        stakingInterfaceAddress = address(this);
    }

    /**
    * @dev Checks executing through delegate call
    */
    modifier onlyDelegateCall()
    {
        require(stakingInterfaceAddress != address(this));
        _;
    }

    /**
    * @dev Checks the existence of the worklock contract
    */
    modifier workLockSet()
    {
        require(address(workLock) != address(0));
        _;
    }

}


/**
* @notice Interface for accessing main contracts from a staking contract
* @dev All methods must be stateless because this code will be executed by delegatecall call, use immutable fields.
* @dev |v1.4.2|
*/
contract StakingInterface is BaseStakingInterface {

    event DepositedAsStaker(address indexed sender, uint256 value, uint16 periods);
    event WithdrawnAsStaker(address indexed sender, uint256 value);
    event Locked(address indexed sender, uint256 value, uint16 periods);
    event Divided(address indexed sender, uint256 index, uint256 newValue, uint16 periods);
    event Minted(address indexed sender);
    event PolicyFeeWithdrawn(address indexed sender, uint256 value);
    event MinFeeRateSet(address indexed sender, uint256 value);
    event ReStakeSet(address indexed sender, bool reStake);
    event ReStakeLocked(address indexed sender, uint16 lockUntilPeriod);
    event WorkerBonded(address indexed sender, address worker);
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
    * @notice Bond worker in the staking escrow
    * @param _worker Worker address
    */
    function bondWorker(address _worker) public onlyDelegateCall {
        escrow.bondWorker(_worker);
        emit WorkerBonded(msg.sender, _worker);
    }

    /**
    * @notice Set `reStake` parameter in the staking escrow
    * @param _reStake Value for parameter
    */
    function setReStake(bool _reStake) public onlyDelegateCall {
        escrow.setReStake(_reStake);
        emit ReStakeSet(msg.sender, _reStake);
    }

    /**
    * @notice Lock `reStake` parameter in the staking escrow
    * @param _lockReStakeUntilPeriod Can't change `reStake` value until this period
    */
    function lockReStake(uint16 _lockReStakeUntilPeriod) public onlyDelegateCall {
        escrow.lockReStake(_lockReStakeUntilPeriod);
        emit ReStakeLocked(msg.sender, _lockReStakeUntilPeriod);
    }

    /**
    * @notice Deposit tokens to the staking escrow
    * @param _value Amount of token to deposit
    * @param _periods Amount of periods during which tokens will be locked
    */
    function depositAsStaker(uint256 _value, uint16 _periods) public onlyDelegateCall {
        require(token.balanceOf(address(this)) >= _value);
        token.approve(address(escrow), _value);
        escrow.deposit(_value, _periods);
        emit DepositedAsStaker(msg.sender, _value, _periods);
    }

    /**
    * @notice Withdraw available amount of tokens from the staking escrow to the staking contract
    * @param _value Amount of token to withdraw
    */
    function withdrawAsStaker(uint256 _value) public onlyDelegateCall {
        escrow.withdraw(_value);
        emit WithdrawnAsStaker(msg.sender, _value);
    }

    /**
    * @notice Lock some tokens or increase lock in the staking escrow
    * @param _value Amount of tokens which should lock
    * @param _periods Amount of periods during which tokens will be locked
    */
    function lock(uint256 _value, uint16 _periods) public onlyDelegateCall {
        escrow.lock(_value, _periods);
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
        public onlyDelegateCall
    {
        escrow.divideStake(_index, _newValue, _periods);
        emit Divided(msg.sender, _index, _newValue, _periods);
    }

    /**
    * @notice Mint tokens in the staking escrow
    */
    function mint() public onlyDelegateCall {
        escrow.mint();
        emit Minted(msg.sender);
    }

    /**
    * @notice Withdraw available policy fees from the policy manager to the staking contract
    */
    function withdrawPolicyFee() public onlyDelegateCall {
        uint256 value = policyManager.withdraw();
        emit PolicyFeeWithdrawn(msg.sender, value);
    }

    /**
    * @notice Set the minimum fee that the staker will accept in the policy manager contract
    */
    function setMinFeeRate(uint256 _minFeeRate) public onlyDelegateCall {
        policyManager.setMinFeeRate(_minFeeRate);
        emit MinFeeRateSet(msg.sender, _minFeeRate);
    }


    /**
    * @notice Prolong active sub stake
    * @param _index Index of the sub stake
    * @param _periods Amount of periods for extending sub stake
    */
    function prolongStake(uint256 _index, uint16 _periods) public onlyDelegateCall {
        escrow.prolongStake(_index, _periods);
        emit Prolonged(msg.sender, _index, _periods);
    }

    /**
    * @notice Set `windDown` parameter in the staking escrow
    * @param _windDown Value for parameter
    */
    function setWindDown(bool _windDown) public onlyDelegateCall {
        escrow.setWindDown(_windDown);
        emit WindDownSet(msg.sender, _windDown);
    }

    /**
    * @notice Bid for tokens by transferring ETH
    */
    function bid(uint256 _value) public payable onlyDelegateCall workLockSet {
        workLock.bid{value: _value}();
        emit Bid(msg.sender, _value);
    }

    /**
    * @notice Cancel bid and refund deposited ETH
    */
    function cancelBid() public onlyDelegateCall workLockSet {
        workLock.cancelBid();
        emit BidCanceled(msg.sender);
    }

    /**
    * @notice Withdraw compensation after force refund
    */
    function withdrawCompensation() public onlyDelegateCall workLockSet {
        workLock.withdrawCompensation();
        emit CompensationWithdrawn(msg.sender);
    }

    /**
    * @notice Claimed tokens will be deposited and locked as stake in the StakingEscrow contract
    */
    function claim() public onlyDelegateCall workLockSet {
        uint256 claimedTokens = workLock.claim();
        emit Claimed(msg.sender, claimedTokens);
    }

    /**
    * @notice Refund ETH for the completed work
    */
    function refund() public onlyDelegateCall workLockSet {
        uint256 refundETH = workLock.refund();
        emit Refund(msg.sender, refundETH);
    }

}
