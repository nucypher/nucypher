pragma solidity ^0.6.1;


import "zeppelin/ownership/Ownable.sol";
import "zeppelin/math/SafeMath.sol";
import "contracts/staking_contracts/AbstractStakingContract.sol";


/**
* @notice Contract acts as delegate for sub-stakers and owner
**/
contract PoolingStakingContract is AbstractStakingContract, Ownable {
    using SafeMath for uint256;

    event TokensDeposited(address indexed sender, uint256 value, uint256 coefficient);
    event TokensWithdrawn(address indexed sender, uint256 value);

    struct Delegator {
        uint256 coefficient;
        uint256 withdrawnTokens;
    }

    uint256 public baseCoefficient;
    uint256 public withdrawnTokens;

    mapping (address => Delegator) public delegators;

    /**
    * @param _router Address of the StakingInterfaceRouter contract
    * @param _ownerCoefficient Base owner's portion of reward
    */
    constructor(
        StakingInterfaceRouter _router,
        uint256 _ownerCoefficient
    )
        public AbstractStakingContract(_router)
    {
        baseCoefficient = _ownerCoefficient;
        Delegator storage delegator = delegators[msg.sender];
        delegator.coefficient = _ownerCoefficient;
    }

    /**
    * @notice Transfer ownership and right to get reward to the new owner
    */
    function transferOwnership(address _newOwner) public override onlyOwner {
        Delegator storage ownerInfo = delegators[owner()];
        Delegator storage newOwnerInfo = delegators[_newOwner];
        newOwnerInfo.coefficient = newOwnerInfo.coefficient.add(ownerInfo.coefficient);
        newOwnerInfo.withdrawnTokens = newOwnerInfo.withdrawnTokens.add(ownerInfo.withdrawnTokens);
        ownerInfo.coefficient = 0;
        ownerInfo.withdrawnTokens = 0;
        super.transferOwnership(_newOwner);
    }

    /**
    * @notice Transfer tokens as delegator
    * @param _value Amount of tokens to transfer
    */
    function depositTokens(uint256 _value) external {
        require(_value > 0, "Value must be not empty");
        baseCoefficient = baseCoefficient.add(_value);
        Delegator storage delegator = delegators[msg.sender];
        delegator.coefficient = delegator.coefficient.add(_value);
        token.safeTransferFrom(msg.sender, address(this), _value);
        emit TokensDeposited(msg.sender, _value, delegator.coefficient);
    }

    /**
    * @notice Withdraw amount of tokens to delegator
    * @param _value Amount of tokens to withdraw
    */
    function withdrawTokens(uint256 _value) public override {
        Delegator storage delegator = delegators[msg.sender];
        uint256 tokens = token.balanceOf(address(this));
        uint256 maxAllowableTokens = tokens.add(withdrawnTokens).mul(delegator.coefficient).div(baseCoefficient);

        delegator.withdrawnTokens = delegator.withdrawnTokens.add(_value);
        require(delegator.withdrawnTokens <= maxAllowableTokens,
            "Requested amount of tokens exceeded allowed portion");

        withdrawnTokens += _value;
        token.safeTransfer(msg.sender, _value);
        emit TokensWithdrawn(msg.sender, _value);
    }

    /**
    * @notice Withdraw available amount of ETH to delegator
    */
    // TODO
    function withdrawETH() public override {}

    /**
    * @notice Calling fallback function is allowed only for the owner
    **/
    function isFallbackAllowed() public override returns (bool) {
        return msg.sender == owner();
    }

}