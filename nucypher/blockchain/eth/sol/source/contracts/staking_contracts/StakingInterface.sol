// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "contracts/staking_contracts/AbstractStakingContract.sol";
import "contracts/NuCypherToken.sol";
import "contracts/IStakingEscrow.sol";
import "contracts/PolicyManager.sol";
import "contracts/WorkLock.sol";
import "threshold/IStaking.sol";


/**
* @notice Base StakingInterface
*/
contract BaseStakingInterface {

    address public immutable stakingInterfaceAddress;
    NuCypherToken public immutable token;
    IStakingEscrow public immutable escrow;
    PolicyManager public immutable policyManager;
    WorkLock public immutable workLock;
    IStaking public immutable tStaking;

    /**
    * @notice Constructor sets addresses of the contracts
    * @param _token Token contract
    * @param _escrow Escrow contract
    * @param _policyManager PolicyManager contract
    * @param _workLock WorkLock contract
    * @param _tStaking Threshold TokenStaking contract
    */
    constructor(
        NuCypherToken _token,
        IStakingEscrow _escrow,
        PolicyManager _policyManager,
        WorkLock _workLock,
        IStaking _tStaking
    ) {
        require(_token.totalSupply() > 0 &&
            _escrow.token() == _token &&
            _policyManager.secondsPerPeriod() > 0 &&
            _tStaking.stakedNu(address(0)) == 0 &&
            // in case there is no worklock contract
            (address(_workLock) == address(0) || _workLock.boostingRefund() > 0));
        token = _token;
        escrow = _escrow;
        policyManager = _policyManager;
        workLock = _workLock;
        tStaking = _tStaking;
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
* @dev |v1.9.1|
*/
contract StakingInterface is BaseStakingInterface {

    event WithdrawnAsStaker(address indexed sender, uint256 value);
    event PolicyFeeWithdrawn(address indexed sender, uint256 value);
    event MinFeeRateSet(address indexed sender, uint256 value);
    event Bid(address indexed sender, uint256 depositedETH);
    event Claimed(address indexed sender, uint256 claimedTokens);
    event Refund(address indexed sender, uint256 refundETH);
    event BidCanceled(address indexed sender);
    event CompensationWithdrawn(address indexed sender);
    event ThresholdNUStaked(
        address indexed sender,
        address indexed operator,
        address beneficiary,
        address authorizer
    );
    event ThresholdNUUnstaked(address indexed sender, address indexed operator, uint96 amount);

    /**
    * @notice Constructor sets addresses of the contracts
    * @param _token Token contract
    * @param _escrow Escrow contract
    * @param _policyManager PolicyManager contract
    * @param _workLock WorkLock contract
    * @param _tStaking Threshold TokenStaking contract
    */
    constructor(
        NuCypherToken _token,
        IStakingEscrow _escrow,
        PolicyManager _policyManager,
        WorkLock _workLock,
        IStaking _tStaking
    )
        BaseStakingInterface(_token, _escrow, _policyManager, _workLock, _tStaking)
    {
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

    /**
    * @notice Copies delegation from the legacy NU staking contract to T staking contract,
    * additionally appointing beneficiary and authorizer roles.
    */
    function stakeNu(
        address operator,
        address payable beneficiary,
        address authorizer
    ) external onlyDelegateCall {
        tStaking.stakeNu(operator, beneficiary, authorizer);
        emit ThresholdNUStaked(msg.sender, operator, beneficiary, authorizer);
    }

    /**
    * @notice Reduces cached legacy NU stake amount by the provided amount.
    */
    function unstakeNu(address operator, uint96 amount) external onlyDelegateCall {
        tStaking.unstakeNu(operator, amount);
        emit ThresholdNUUnstaked(msg.sender, operator, amount);
    }
}
