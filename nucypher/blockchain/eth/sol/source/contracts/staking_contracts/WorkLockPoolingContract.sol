// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;

import "zeppelin/ownership/Ownable.sol";
import "zeppelin/math/SafeMath.sol";
import "contracts/staking_contracts/AbstractStakingContract.sol";

/**
 * @notice Contract acts as delegate for sub-stakers and owner
 * @author @vzotova and @roma_k
 **/
contract WorkLockPoolingContract is InitializableStakingContract, Ownable {
    using SafeMath for uint256;
    using Address for address payable;
    using SafeERC20 for NuCypherToken;

    event TokensDeposited(
        address indexed sender,
        uint256 value,
        uint256 depositedTokens
    );
    event TokensWithdrawn(
        address indexed sender,
        uint256 value,
        uint256 depositedTokens
    );
    event ETHWithdrawn(address indexed sender, uint256 value);
    event DepositSet(address indexed sender, bool value);
    event Claimed(address indexed sender, uint256 claimedTokens);
    event Refund(address indexed sender, uint256 refundETH);

    struct Delegator {
        uint256 depositedTokens;

        uint256 withdrawnReward;
        uint256 withdrawnETH;

        uint256 paidETH;

        uint256 depositedETHWorkLock;
        uint256 refundedETHWorkLock;
        bool claimedWorkLockTokens;
    }

    StakingEscrow public escrow;
    WorkLock public workLock;

    uint256 public totalDepositedTokens;
    uint256 public worklockClaimedTokens;

    uint256 public totalWithdrawnReward;
    uint256 public totalWithdrawnETH;

    uint256 public totalWorklockETHReceived;
    uint256 public totalWorklockETHRefunded;
    uint256 public totalWorklockETHWithdrawn;

    uint256 public ownerFraction;
    uint256 public ownerWithdrawnReward;
    uint256 public ownerWithdrawnETH;

    mapping(address => Delegator) public delegators;
    bool depositIsEnabled = true;

    /**
     * @notice Initialize function for using with OpenZeppelin proxy
     */
    function initialize(
        uint256 _ownerFraction,
        StakingInterfaceRouter _router
    ) public initializer {
        InitializableStakingContract.initialize(_router);
        // Ownable.initialize();
        escrow = _router.target().escrow();
        workLock = _router.target().workLock();
        ownerFraction = _ownerFraction;
    }

    /**
     * @notice Enabled deposit
     */
    function enableDeposit() external onlyOwner {
        depositIsEnabled = true;
        emit DepositSet(msg.sender, depositIsEnabled);
    }

    /**
     * @notice Disable deposit
     */
    function disableDeposit() external onlyOwner {
        depositIsEnabled = false;
        emit DepositSet(msg.sender, depositIsEnabled);
    }

    /**
     * @notice Transfer tokens as delegator
     * @param _value Amount of tokens to transfer
     */
    function depositTokens(uint256 _value) external {
        require(depositIsEnabled, "Deposit must be enabled");
        require(_value > 0, "Value must be not empty");
        totalDepositedTokens = totalDepositedTokens.add(_value);
        Delegator storage delegator = delegators[msg.sender];
        delegator.depositedTokens += _value;
        token.safeTransferFrom(msg.sender, address(this), _value);
        emit TokensDeposited(msg.sender, _value, delegator.depositedTokens);
    }

    /**
     * @notice delagetor can transfer ETH to directly workLock
     */
    function escrowETH() external payable {
        Delegator storage delegator = delegators[msg.sender];
        delegator.depositedETHWorkLock = delegator.depositedETHWorkLock.add(msg.value);
        totalWorklockETHReceived = totalWorklockETHReceived.add(msg.value);
        workLock.bid{value: msg.value}();
    }

    /**
     * @dev Hide method from StakingInterface
     */
    function bid(uint256 _value) public payable {}

    /**
     * @dev Hide method from StakingInterface
     */
    function withdrawCompensation() public {}

    /**
     * @dev Hide method from StakingInterface
     */
    function cancelBid() public {}

    /**
     * @notice Claim tokens in WorkLock and save number of claimed tokens
     */
    function claim() public {
        worklockClaimedTokens = workLock.claim();
        totalDepositedTokens = totalDepositedTokens.add(worklockClaimedTokens);
        emit Claimed(msg.sender, worklockClaimedTokens);
    }

    /**
     * @notice Calculate and save number of claimed tokens for specified delegator
     */
    function claimTokens(Delegator storage _delegator) internal {
        if (worklockClaimedTokens == 0 ||
            _delegator.depositedETHWorkLock == 0 ||
            _delegator.claimedWorkLockTokens)
        {
            return;
        }

        uint256 claimedTokens = _delegator.depositedETHWorkLock.mul(worklockClaimedTokens)
            .div(totalWorklockETHReceived);

        _delegator.depositedTokens += claimedTokens;
        _delegator.claimedWorkLockTokens = true;
        emit Claimed(msg.sender, claimedTokens);
    }

    /**
     * @notice Get available reward for all delegators and owner
     */
    function getAvailableReward() public view returns (uint256) {
        uint256 stakedTokens = escrow.getAllTokens(address(this));
        uint256 freeTokens = token.balanceOf(address(this));
        uint256 reward = stakedTokens + freeTokens - totalDepositedTokens;
        if (reward > freeTokens) {
            return freeTokens;
        }
        return reward;
    }

    /**
     * @notice Get cumulative reward
     */
    function getCumulativeReward() public view returns (uint256) {
        return getAvailableReward().add(totalWithdrawnReward);
    }

    /**
     * @notice Get available reward in tokens for pool owner
     */
    function getAvailableOwnerReward() public view returns (uint256) {
        uint256 reward = getCumulativeReward();

        uint256 maxAllowableReward;
        if (totalDepositedTokens != 0) {
            maxAllowableReward = reward.mul(ownerFraction).div(
                totalDepositedTokens.add(ownerFraction)
            );
        } else {
            maxAllowableReward = reward;
        }

        return maxAllowableReward.sub(ownerWithdrawnReward);
    }

    /**
     * @notice Get available reward in tokens for delegator
     */
    function getAvailableReward(address _delegator)
        public
        view
        returns (uint256)
    {
        if (totalDepositedTokens == 0) {
            return 0;
        }

        uint256 reward = getCumulativeReward();
        Delegator storage delegator = delegators[_delegator];
        uint256 maxAllowableReward = reward.mul(delegator.depositedTokens).div(
            totalDepositedTokens.add(ownerFraction)
        );

        return
            maxAllowableReward > delegator.withdrawnReward
                ? maxAllowableReward - delegator.withdrawnReward
                : 0;
    }

    /**
     * @notice Withdraw reward in tokens to owner
     */
    function withdrawOwnerReward() public onlyOwner {
        uint256 balance = token.balanceOf(address(this));
        uint256 availableReward = getAvailableOwnerReward();

        if (availableReward > balance) {
            availableReward = balance;
        }
        require(
            availableReward > 0,
            "There is no available reward to withdraw"
        );
        ownerWithdrawnReward = ownerWithdrawnReward.add(availableReward);
        totalWithdrawnReward = totalWithdrawnReward.add(availableReward);

        token.safeTransfer(msg.sender, availableReward);
        emit TokensWithdrawn(msg.sender, availableReward, 0);
    }

    /**
     * @notice Withdraw amount of tokens to delegator
     * @param _value Amount of tokens to withdraw
     */
    function withdrawTokens(uint256 _value) public override {
        uint256 balance = token.balanceOf(address(this));
        require(_value <= balance, "Not enough tokens in the contract");

        Delegator storage delegator = delegators[msg.sender];
        claimTokens(delegator);

        uint256 availableReward = getAvailableReward(msg.sender);

        require(
            _value <= availableReward + delegator.depositedTokens,
            "Requested amount of tokens exceeded allowed portion"
        );

        if (_value <= availableReward) {
            delegator.withdrawnReward += _value;
            totalWithdrawnReward += _value;
        } else {
            delegator.withdrawnReward = delegator.withdrawnReward.add(
                availableReward
            );
            totalWithdrawnReward = totalWithdrawnReward.add(availableReward);

            uint256 depositToWithdraw = _value - availableReward;
            uint256 newDepositedTokens = delegator.depositedTokens -
                depositToWithdraw;
            uint256 newWithdrawnReward = delegator
                .withdrawnReward
                .mul(newDepositedTokens)
                .div(delegator.depositedTokens);
            uint256 newWithdrawnETH = delegator
                .withdrawnETH
                .mul(newDepositedTokens)
                .div(delegator.depositedTokens);
            totalDepositedTokens -= depositToWithdraw;
            totalWithdrawnReward -= (delegator.withdrawnReward -
                newWithdrawnReward);
            totalWithdrawnETH -= (delegator.withdrawnETH - newWithdrawnETH);
            delegator.depositedTokens = newDepositedTokens;
            delegator.withdrawnReward = newWithdrawnReward;
            delegator.withdrawnETH = newWithdrawnETH;
        }

        token.safeTransfer(msg.sender, _value);
        emit TokensWithdrawn(msg.sender, _value, delegator.depositedTokens);
    }

    /**
     * @notice Get available ether for owner
     */
    function getAvailableOwnerETH() public view returns (uint256) {
        // TODO boilerplate code
        uint256 balance = address(this).balance;
        balance = balance.add(totalWithdrawnETH).add(totalWorklockETHRefunded).sub(totalWorklockETHWithdrawn);
        uint256 maxAllowableETH = balance.mul(ownerFraction).div(
            totalDepositedTokens.add(ownerFraction)
        );

        uint256 availableETH = maxAllowableETH.sub(ownerWithdrawnETH);
        if (availableETH > balance) {
            availableETH = balance;
        }
        return availableETH;
    }

    /**
     * @notice Get available ether for delegator
     */
    function getAvailableETH(address _delegator) public view returns (uint256) {
        Delegator storage delegator = delegators[_delegator];
        // TODO boilerplate code
        uint256 balance = address(this).balance;
        balance = balance.add(totalWithdrawnETH).add(totalWorklockETHRefunded).sub(totalWorklockETHWithdrawn);
        uint256 maxAllowableETH = balance.mul(delegator.depositedTokens).div(
            totalDepositedTokens.add(ownerFraction)
        );

        uint256 availableETH = maxAllowableETH.sub(delegator.withdrawnETH);
        if (availableETH > balance) {
            availableETH = balance;
        }
        return availableETH;
    }

    /**
     * @notice Withdraw available amount of ETH to delegator
     */
    function withdrawOwnerETH() public onlyOwner {
        uint256 availableETH = getAvailableOwnerETH();
        require(availableETH > 0, "There is no available ETH to withdraw");

        ownerWithdrawnETH = ownerWithdrawnETH.add(availableETH);
        totalWithdrawnETH = totalWithdrawnETH.add(availableETH);

        msg.sender.sendValue(availableETH);
        emit ETHWithdrawn(msg.sender, availableETH);
    }

    /**
     * @notice Withdraw available amount of ETH to delegator
     */
    function withdrawETH() public override {
        Delegator storage delegator = delegators[msg.sender];
        claimTokens(delegator);

        uint256 availableETH = getAvailableETH(msg.sender);
        require(availableETH > 0, "There is no available ETH to withdraw");
        delegator.withdrawnETH = delegator.withdrawnETH.add(availableETH);

        totalWithdrawnETH = totalWithdrawnETH.add(availableETH);
        msg.sender.sendValue(availableETH);
        emit ETHWithdrawn(msg.sender, availableETH);
    }

    /**
     * @notice Withdraw compensation and refund from WorkLock and save these numbers
     */
    function refund() public {
        uint256 balance = address(this).balance;
        if (workLock.compensation(address(this)) > 0) {
            workLock.withdrawCompensation();
        }
        workLock.refund();
        uint256 refundETH = address(this).balance - balance;
        totalWorklockETHRefunded += refundETH;
        emit Refund(msg.sender, refundETH);
    }

    /**
     * @notice Get available refund for delegator
     */
    function getAvailableRefund(address _delegator) public view returns (uint256) {
        Delegator storage delegator = delegators[_delegator];
        uint256 maxAllowableETH = totalWorklockETHRefunded.mul(delegator.depositedETHWorkLock)
            .div(totalWorklockETHReceived);

        uint256 availableETH = maxAllowableETH.sub(delegator.refundedETHWorkLock);
        uint256 balance = totalWorklockETHRefunded.sub(totalWorklockETHWithdrawn);

        if (availableETH > balance) {
            availableETH = balance;
        }
        return availableETH;
    }

    /**
     * @notice Withdraw available amount of ETH to delegator
     */
    function withdrawRefund() external {
        uint256 availableETH = getAvailableRefund(msg.sender);
        require(availableETH > 0, "There is no available ETH to withdraw");

        Delegator storage delegator = delegators[msg.sender];
        delegator.refundedETHWorkLock = delegator.refundedETHWorkLock.add(availableETH);

        totalWorklockETHWithdrawn = totalWorklockETHWithdrawn.add(availableETH);
        msg.sender.sendValue(availableETH);
        emit Refund(msg.sender, availableETH);
    }

    /**
     * @notice Calling fallback function is allowed only for the owner
     */
    function isFallbackAllowed() public override view returns (bool) {
        return msg.sender == owner();
    }
}
