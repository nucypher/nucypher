pragma solidity ^0.6.1;


import "zeppelin/ownership/Ownable.sol";
import "zeppelin/math/SafeMath.sol";
import "contracts/staking_contracts/AbstractStakingContract.sol";


/**
* @notice Contract acts as delegate for sub-stakers and owner
**/
contract PoolingStakingContract is AbstractStakingContract, Ownable {
    using SafeMath for uint256;

    event TokensDeposited(address indexed sender, uint256 value, uint256 depositedTokens);
    event TokensWithdrawn(address indexed sender, uint256 value);
    event ETHWithdrawn(address indexed sender, uint256 value);
    event ShareTransferred(address indexed previousOwner, address indexed newOwner, uint256 depositedTokens);

    struct Delegator {
        uint256 depositedTokens;
        uint256 withdrawnTokens;
        uint256 withdrawnETH;
    }

    uint256 public totalDepositedTokens;
    uint256 public totalWithdrawnTokens;
    uint256 public totalWithdrawnETH;

    mapping (address => Delegator) public delegators;

    /**
    * @param _router Address of the StakingInterfaceRouter contract
    * @param _ownerReward Base owner's portion of reward
    */
    constructor(
        StakingInterfaceRouter _router,
        uint256 _ownerReward
    )
        public AbstractStakingContract(_router)
    {
        totalDepositedTokens = _ownerReward;
        Delegator storage delegator = delegators[msg.sender];
        delegator.depositedTokens = _ownerReward;
    }

    /**
    * @notice Transfer ownership and right to get reward to the new owner
    */
    function transferOwnership(address _newOwner) public override onlyOwner {
        Delegator storage ownerInfo = delegators[owner()];
        Delegator storage newOwnerInfo = delegators[_newOwner];

        newOwnerInfo.depositedTokens = newOwnerInfo.depositedTokens.add(ownerInfo.depositedTokens);
        newOwnerInfo.withdrawnTokens = newOwnerInfo.withdrawnTokens.add(ownerInfo.withdrawnTokens);
        newOwnerInfo.withdrawnETH = newOwnerInfo.withdrawnETH.add(ownerInfo.withdrawnETH);
        emit ShareTransferred(owner(), _newOwner, ownerInfo.depositedTokens);

        ownerInfo.depositedTokens = 0;
        ownerInfo.withdrawnTokens = 0;
        ownerInfo.withdrawnETH = 0;
        super.transferOwnership(_newOwner);
    }

    /**
    * @notice Transfer tokens as delegator
    * @param _value Amount of tokens to transfer
    */
    function depositTokens(uint256 _value) external {
        require(_value > 0, "Value must be not empty");
        totalDepositedTokens = totalDepositedTokens.add(_value);
        Delegator storage delegator = delegators[msg.sender];
        delegator.depositedTokens = delegator.depositedTokens.add(_value);
        token.safeTransferFrom(msg.sender, address(this), _value);
        emit TokensDeposited(msg.sender, _value, delegator.depositedTokens);
    }

    /**
    * @notice Get available tokens for delegator
    */
    function getAvailableTokens(address _delegator) public view returns (uint256) {
        Delegator storage delegator = delegators[_delegator];
        uint256 tokens = token.balanceOf(address(this));
        uint256 maxAllowableTokens = tokens.add(totalWithdrawnTokens).mul(delegator.depositedTokens).div(totalDepositedTokens);

        uint256 availableTokens = maxAllowableTokens.sub(delegator.withdrawnTokens);
        // TODO maybe return full value even if it's more than contract balance?
        if (availableTokens > tokens) {
            availableTokens = tokens;
        }
        return availableTokens;
    }

    /**
    * @notice Withdraw amount of tokens to delegator
    * @param _value Amount of tokens to withdraw
    */
    function withdrawTokens(uint256 _value) public override {
        uint256 availableTokens = getAvailableTokens(msg.sender);
        require(_value <= availableTokens, "Requested amount of tokens exceeded allowed portion");

        Delegator storage delegator = delegators[msg.sender];
        delegator.withdrawnTokens = delegator.withdrawnTokens.add(_value);

        // TODO fix this
        totalWithdrawnTokens = totalWithdrawnTokens.add(_value);
        token.safeTransfer(msg.sender, _value);
        emit TokensWithdrawn(msg.sender, _value);
    }

    /**
    * @notice Get available ether for delegator
    */
    function getAvailableETH(address _delegator) public view returns (uint256) {
        Delegator storage delegator = delegators[_delegator];
        uint256 balance = address(this).balance;
        uint256 maxAllowableETH = balance.add(totalWithdrawnETH).mul(delegator.depositedTokens).div(totalDepositedTokens);

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
        uint256 availableETH = getAvailableETH(msg.sender);
        require(availableETH > 0, "There is no available ETH to withdraw");

        Delegator storage delegator = delegators[msg.sender];
        delegator.withdrawnETH = delegator.withdrawnETH.add(availableETH);

        totalWithdrawnETH = totalWithdrawnETH.add(availableETH);
        msg.sender.sendValue(availableETH);
        emit ETHWithdrawn(msg.sender, availableETH);
    }

    /**
    * @notice Calling fallback function is allowed only for the owner
    **/
    function isFallbackAllowed() public override returns (bool) {
        return msg.sender == owner();
    }

}
