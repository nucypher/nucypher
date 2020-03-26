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
    uint256 public ownerCoefficient;
    uint256 public ownerWithdrawnTokens;

    /**
    * @param _router Address of the StakingInterfaceRouter contract
    * @param _ownerCoefficient Address of the NuCypher token contract
    */
    constructor(
        StakingInterfaceRouter _router,
        uint256 _ownerCoefficient
    )
        public AbstractStakingContract(_router)
    {
        ownerCoefficient = _ownerCoefficient;
        baseCoefficient = _ownerCoefficient;
    }

    function depositTokens(uint256 _value) external {
        require(_value > 0, "Value must be not empty");
        baseCoefficient = baseCoefficient.add(_value);
        Delegator storage delegator = delegators[msg.sender];
        delegator.coefficient = delegator.coefficient.add(_value);
        token.safeTransferFrom(msg.sender, address(this), _value);
        emit TokensDeposited(msg.sender, _value, delegator.coefficient);
    }

    function withdrawOwnerTokens(uint256 _value) external onlyOwner {
        ownerWithdrawnTokens = ownerWithdrawnTokens.add(_value);
        withdrawTokens(_value, ownerCoefficient, ownerWithdrawnTokens);
    }

    function withdrawTokens(uint256 _value) public override {
        Delegator storage delegator = delegators[msg.sender];
        delegator.withdrawnTokens = delegator.withdrawnTokens.add(_value);
        withdrawTokens(_value, delegator.coefficient, delegator.withdrawnTokens);
    }

    function withdrawTokens(uint256 _value, uint256 _senderCoefficient, uint256 _senderWithdrawnTokens) internal {
        uint256 tokens = token.balanceOf(address(this));
        require(_value <= tokens, "Value to withdraw must be less than amount of tokens in the contract");

        uint256 maxAllowableTokens = tokens.add(withdrawnTokens).mul(_senderCoefficient).div(baseCoefficient);
        require(_senderWithdrawnTokens <= maxAllowableTokens,
            "Requested amount of tokens exceeded allowed portion");
        withdrawnTokens += _value;
        token.safeTransfer(msg.sender, _value);
        emit TokensWithdrawn(msg.sender, _value);
    }

    // TODO
    function withdrawETH() public override {}

    /**
    * @notice Calling fallback function is allowed only for the owner
    **/
    function isFallbackAllowed() public override returns (bool) {
        return msg.sender == owner();
    }

}