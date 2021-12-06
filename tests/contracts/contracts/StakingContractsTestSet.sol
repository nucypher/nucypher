// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "contracts/NuCypherToken.sol";
import "contracts/staking_contracts/AbstractStakingContract.sol";


/**
* @notice Contract for using in staking contracts tests
*/
contract StakingEscrowForStakingContractMock {

    NuCypherToken public immutable token;
    address public node;
    uint256 public value;
    uint256 public lockedValue;
    bool public snapshots;

    constructor(NuCypherToken _token) {
        token = _token;
    }

    function deposit(address _node, uint256 _value) external {
        node = _node;
        value += _value;
        lockedValue += _value;
        token.transferFrom(msg.sender, address(this), _value);
    }

    function withdraw(uint256 _value) public {
        value -= _value;
        token.transfer(msg.sender, _value);
    }

    function withdrawAll() external {
        withdraw(value);
    }

    function getAllTokens(address) external view returns (uint256) {
        return value;
    }

    function setSnapshots(bool _snapshotsEnabled) external {
        snapshots = _snapshotsEnabled;
    }
}


/**
* @notice Contract for staking contract tests
*/
contract PolicyManagerForStakingContractMock {

    uint32 public immutable secondsPerPeriod = 1;
    uint256 public minFeeRate;

    function withdraw() public returns (uint256) {
        uint256 value = address(this).balance;
        require(value > 0);
        payable(msg.sender).transfer(value);
        return value;
    }

    function setMinFeeRate(uint256 _minFeeRate) public {
        minFeeRate = _minFeeRate;
    }

    function additionalMethod(uint256 _minFeeRate) public {
        minFeeRate = _minFeeRate;
    }

    receive() external payable {}
}


/**
* @notice Contract for staking contract tests
*/
contract WorkLockForStakingContractMock {

    uint256 public immutable boostingRefund = 1;
    uint256 public claimed;
    uint256 public depositedETH;
    uint256 public compensationValue;
    uint256 public refundETH;
    uint256 public futureClaim;

    function bid() external payable {
        depositedETH = msg.value;
    }

    function cancelBid() external {
        uint256 value = depositedETH;
        depositedETH = 0;
        payable(msg.sender).transfer(value);
    }

    function sendCompensation() external payable {
        compensationValue = msg.value;
    }

    function compensation(address) public view returns (uint256) {
        return compensationValue;
    }

    function withdrawCompensation() external {
        uint256 value = compensationValue;
        compensationValue = 0;
        payable(msg.sender).transfer(value);
    }

    function setClaimedTokens(uint256 _claimedTokens) external {
        futureClaim = _claimedTokens;
    }

    function claim() external returns (uint256) {
        if (futureClaim == 0) {
            claimed += 1;
        } else {
            claimed += futureClaim;
        }
        return claimed;
    }

    function sendRefund() external payable {
        refundETH = msg.value;
    }

    function refund() external returns (uint256) {
        uint256 value = refundETH;
        refundETH = 0;
        payable(msg.sender).transfer(value);
        return value;
    }

}


/**
* @notice Contract for staking contract tests
*/
contract ThresholdStakingForStakingContractMock {

    address public operator;
    address payable public beneficiary;
    address public authorizer;
    uint96 public stakedNuInT;

    function stakedNu(address) external view returns (uint256) {
        return 0;
    }

    function stakeNu(
        address _operator,
        address payable _beneficiary,
        address _authorizer
    ) external {
        operator = _operator;
        beneficiary = _beneficiary;
        authorizer = _authorizer;
        stakedNuInT = 1000;
    }

    function unstakeNu(address _operator, uint96 _amount) external {
        require(operator == _operator);
        stakedNuInT -= _amount;
    }
}


/**
* @notice Contract for staking contract tests
*/
contract StakingInterfaceMockV1 {

    address public immutable token = address(1);
    address public immutable escrow = address(1);

    function firstMethod() public pure {}

    function secondMethod() public pure returns (uint256) {
        return 20;
    }

}


/**
* @notice Contract for staking contract tests
*/
contract StakingInterfaceMockV2 {

    address public immutable token = address(1);
    address public immutable escrow = address(1);

    receive() external payable {}

    function firstMethod(uint256) public pure {}

    function secondMethod() public pure returns (uint256) {
        return 15;
    }

    function thirdMethod() public pure {}

}


/**
* @dev Interface that could be destroyed by selfdestruct
*/
contract DestroyableStakingInterface {

    address public immutable token = address(1);
    address public immutable escrow = address(1);

    function method() public pure returns (uint256) {
        return 15;
    }

    function destroy() public {
        selfdestruct(payable(msg.sender));
    }

}


/**
* @notice Simple implementation of AbstractStakingContract
*/
contract SimpleStakingContract is AbstractStakingContract, Ownable {
    using SafeERC20 for NuCypherToken;
    using Address for address payable;

    /**
    * @param _router Address of the StakingInterfaceRouter contract
    */
    constructor(StakingInterfaceRouter _router) AbstractStakingContract(_router) {}

    /**
    * @notice Withdraw available amount of tokens to owner
    * @param _value Amount of token to withdraw
    */
    function withdrawTokens(uint256 _value) public override onlyOwner {
        token.safeTransfer(msg.sender, _value);
    }

    /**
    * @notice Withdraw available ETH to the owner
    */
    function withdrawETH() public override onlyOwner {
        uint256 balance = address(this).balance;
        require(balance != 0);
        payable(msg.sender).sendValue(balance);
    }

    /**
    * @notice Calling fallback function is allowed only for the owner
    */
    function isFallbackAllowed() public view override returns (bool) {
        return msg.sender == owner();
    }

}


interface IExtendedStakingEscrow is IStakingEscrow {
    function deposit(address, uint256) external;
    function withdraw(uint256) external;
}

/**
* @notice Contract for staking contract tests
*/
contract ExtendedStakingInterface is StakingInterface {

    event DepositedAsStaker(address indexed sender, uint256 value);

    constructor(
        NuCypherToken _token,
        IStakingEscrow _escrow,
        PolicyManager _policyManager,
        WorkLock _workLock,
        IStaking _tStaking
    )
        StakingInterface(_token, _escrow, _policyManager, _workLock, _tStaking)
    {
    }

    function depositAsStaker(uint256 _value) public onlyDelegateCall {
        require(token.balanceOf(address(this)) >= _value);
        token.approve(address(escrow), _value);
        IExtendedStakingEscrow(address(escrow)).deposit(address(this), _value);
        emit DepositedAsStaker(msg.sender, _value);
    }

}
