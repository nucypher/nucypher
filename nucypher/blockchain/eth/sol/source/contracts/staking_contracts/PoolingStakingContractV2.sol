// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;

import "zeppelin/ownership/Ownable.sol";
import "zeppelin/math/SafeMath.sol";
import "contracts/staking_contracts/AbstractStakingContract.sol";

/**
 * @notice Contract acts as delegate for sub-stakers
 **/
contract PoolingStakingContractV2 is InitializableStakingContract, Ownable {
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

    struct Delegator {
        uint256 depositedTokens;
        uint256 withdrawnReward;
        uint256 withdrawnETH;
    }

    /// Defines base fraction and precision of worker fraction. Value 100 defines 1 worker fraction is 1% of reward
    uint256 public constant BASIS_FRACTION = 100;

    StakingEscrow public escrow;
    address public workerOwner;

    uint256 public totalDepositedTokens;
    uint256 public totalWithdrawnReward;
    uint256 public totalWithdrawnETH;

    uint256 workerFraction;
    uint256 public workerWithdrawnReward;

    mapping(address => Delegator) public delegators;
    bool public depositIsEnabled = true;

    /**
     * @notice Initialize function for using with OpenZeppelin proxy
     * @param _workerFraction Share of token reward that worker node owner will get.
     * Use value up to BASIS_FRACTION, if _workerFraction = BASIS_FRACTION -> means 100% reward as commission
     * @param _router StakingInterfaceRouter address
     * @param _workerOwner Owner of worker node, only this address can withdraw worker commission
     */
    function initialize(
        uint256 _workerFraction,
        StakingInterfaceRouter _router,
        address _workerOwner
    ) public initializer {
        require(_workerOwner != address(0) && _workerFraction <= BASIS_FRACTION);
        InitializableStakingContract.initialize(_router);
        _transferOwnership(msg.sender);
        escrow = _router.target().escrow();
        workerFraction = _workerFraction;
        workerOwner = _workerOwner;
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
     * @notice Calculate worker's fraction depending on deposited tokens
     */
    function getWorkerFraction() public view returns (uint256) {
        return workerFraction;
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
        delegator.depositedTokens = delegator.depositedTokens.add(_value);
        token.safeTransferFrom(msg.sender, address(this), _value);
        emit TokensDeposited(msg.sender, _value, delegator.depositedTokens);
    }

    /**
     * @notice Get available reward for all delegators and owner
     */
    function getAvailableReward() public view returns (uint256) {
        uint256 stakedTokens = escrow.getAllTokens(address(this));
        uint256 freeTokens = token.balanceOf(address(this));
        uint256 reward = stakedTokens.add(freeTokens).sub(totalDepositedTokens);
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
     * @notice Get available reward in tokens for worker node owner
     */
    function getAvailableWorkerReward() public view returns (uint256) {
        uint256 reward = getCumulativeReward();

        uint256 maxAllowableReward;
        if (totalDepositedTokens != 0) {
            uint256 fraction = getWorkerFraction();
            maxAllowableReward = reward.mul(fraction).div(BASIS_FRACTION);
        } else {
            maxAllowableReward = reward;
        }

        if (maxAllowableReward > workerWithdrawnReward) {
            return maxAllowableReward - workerWithdrawnReward;
        }
        return 0;
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
        uint256 fraction = getWorkerFraction();
        uint256 maxAllowableReward = reward.mul(delegator.depositedTokens).mul(BASIS_FRACTION - fraction).div(
            totalDepositedTokens.mul(BASIS_FRACTION)
        );

        return
            maxAllowableReward > delegator.withdrawnReward
                ? maxAllowableReward - delegator.withdrawnReward
                : 0;
    }

    /**
     * @notice Withdraw reward in tokens to worker node owner
     */
    function withdrawWorkerReward() external {
        require(msg.sender == workerOwner);
        uint256 balance = token.balanceOf(address(this));
        uint256 availableReward = getAvailableWorkerReward();

        if (availableReward > balance) {
            availableReward = balance;
        }
        require(
            availableReward > 0,
            "There is no available reward to withdraw"
        );
        workerWithdrawnReward = workerWithdrawnReward.add(availableReward);
        totalWithdrawnReward = totalWithdrawnReward.add(availableReward);

        token.safeTransfer(msg.sender, availableReward);
        emit TokensWithdrawn(msg.sender, availableReward, 0);
    }

    /**
     * @notice Withdraw reward to delegator
     * @param _value Amount of tokens to withdraw
     */
    function withdrawTokens(uint256 _value) public override {
        uint256 balance = token.balanceOf(address(this));
        require(_value <= balance, "Not enough tokens in the contract");

        Delegator storage delegator = delegators[msg.sender];
        uint256 availableReward = getAvailableReward(msg.sender);

        require( _value <= availableReward, "Requested amount of tokens exceeded allowed portion");
        delegator.withdrawnReward = delegator.withdrawnReward.add(_value);
        totalWithdrawnReward = totalWithdrawnReward.add(_value);

        token.safeTransfer(msg.sender, _value);
        emit TokensWithdrawn(msg.sender, _value, delegator.depositedTokens);
    }

    /**
     * @notice Withdraw reward, deposit and fee to delegator
     */
    function withdrawAll() public {
        uint256 balance = token.balanceOf(address(this));

        Delegator storage delegator = delegators[msg.sender];
        uint256 availableReward = getAvailableReward(msg.sender);
        uint256 value = availableReward.add(delegator.depositedTokens);
        require(value <= balance, "Not enough tokens in the contract");

        // TODO remove double reading
        uint256 availableWorkerReward = getAvailableWorkerReward();

        // potentially could be less then due reward
        uint256 availableETH = getAvailableETH(msg.sender);

        // prevent losing reward for worker after calculations
        uint256 workerReward = availableWorkerReward.mul(delegator.depositedTokens).div(totalDepositedTokens);
        if (workerReward > 0) {
            require(value.add(workerReward) <= balance, "Not enough tokens in the contract");
            token.safeTransfer(workerOwner, workerReward);
            emit TokensWithdrawn(workerOwner, workerReward, 0);
        }

        uint256 withdrawnToDecrease = workerWithdrawnReward.mul(delegator.depositedTokens).div(totalDepositedTokens);

        workerWithdrawnReward = workerWithdrawnReward.sub(withdrawnToDecrease);
        totalWithdrawnReward = totalWithdrawnReward.sub(withdrawnToDecrease).sub(delegator.withdrawnReward);
        totalDepositedTokens = totalDepositedTokens.sub(delegator.depositedTokens);

        delegator.withdrawnReward = 0;
        delegator.depositedTokens = 0;

        token.safeTransfer(msg.sender, value);
        emit TokensWithdrawn(msg.sender, value, 0);

        totalWithdrawnETH = totalWithdrawnETH.sub(delegator.withdrawnETH);
        delegator.withdrawnETH = 0;
        if (availableETH > 0) {
            msg.sender.sendValue(availableETH);
            emit ETHWithdrawn(msg.sender, availableETH);
        }
    }

    /**
     * @notice Get available ether for delegator
     */
    function getAvailableETH(address _delegator) public view returns (uint256) {
        Delegator storage delegator = delegators[_delegator];
        uint256 balance = address(this).balance;
        // ETH balance + already withdrawn
        balance = balance.add(totalWithdrawnETH);
        uint256 maxAllowableETH = balance.mul(delegator.depositedTokens).div(totalDepositedTokens);

        uint256 availableETH = maxAllowableETH.sub(delegator.withdrawnETH);
        if (availableETH > balance) {
            availableETH = balance;
        }
        return availableETH;
    }

    /**
     * @notice Withdraw available amount of ETH to delegator
     */
    function withdrawETH() public override {
        Delegator storage delegator = delegators[msg.sender];
        uint256 availableETH = getAvailableETH(msg.sender);
        require(availableETH > 0, "There is no available ETH to withdraw");
        delegator.withdrawnETH = delegator.withdrawnETH.add(availableETH);

        totalWithdrawnETH = totalWithdrawnETH.add(availableETH);
        msg.sender.sendValue(availableETH);
        emit ETHWithdrawn(msg.sender, availableETH);
    }

    /**
     * @notice Calling fallback function is allowed only for the owner
     */
    function isFallbackAllowed() public override view returns (bool) {
        return msg.sender == owner();
    }
}
