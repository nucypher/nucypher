pragma solidity ^0.4.0;


import "./MineableToken.sol";
import "./lib/ExponentMath.sol";
import "./zeppelin/math/SafeMath.sol";


/**
* @notice Contract for minting tokens
**/
contract Miner {
    using SafeMath for uint256;

    uint64 constant ITERATIONS = 30;

    MineableToken token;
    //TODO calculate lastMintedPoint
    uint256 public lastMintedPoint;
    uint256 public rate;
    uint256 public fractions;
    uint256 public maxValue;
    uint256 public multiplicator;
    uint256 supply;

    /**
    * @notice The Miner constructor sets address of token contract and coefficients for mining
    * @param _token Token contract
    * @param _rate Curve growing rate
    * @param _fractions Coefficient for fractions
    **/
    function Miner(MineableToken _token, uint256 _rate, uint256 _fractions) {
        require(_rate != 0 && _fractions != 0);
        token = _token;
        maxValue = token.futureSupply() - token.totalSupply();
        lastMintedPoint = 0;
        rate = _rate;
        fractions = _fractions;
        multiplicator = fractions;
        supply = 0;
    }

    /**
    * @dev Check reward.
    * @param _lockedValue The amount of tokens that were locked.
    * @param _lockedBlocks The amount of blocks during which tokens were locked.
    * @return Reward is empty or not
    **/
    function isEmptyReward(uint256 _lockedValue, uint256 _lockedBlocks)
        constant returns (bool)
    {
        return _lockedValue * _lockedBlocks < rate;
    }

    /**
    * @notice Function to mint tokens for sender
    * @param _to The address that will receive the minted tokens.
    * @param _lockedValue The amount of tokens that were locked.
    * @param _lockedBlocks The amount of blocks during which tokens were locked.
    * @param _decimals The amount of locked tokens and blocks in decimals.
    * @return Amount of minted tokens.
    */
    function mint(
        address _to,
        uint256 _lockedValue,
        uint256 _lockedBlocks,
        uint256 _decimals
    )
        internal returns (uint256 amount, uint256 decimals)
    {
        uint256 value = _lockedValue.mul(_lockedBlocks).add(_decimals);
        uint256 newMintedPoint = lastMintedPoint.add(value.div(rate));
        if (newMintedPoint == lastMintedPoint) {
            return (0, 0);
        }
        lastMintedPoint = newMintedPoint;
        uint256 currentSupply = ExponentMath.exponentialFunction(
            lastMintedPoint, maxValue, fractions, multiplicator, ITERATIONS);
        amount = currentSupply.sub(supply);
        decimals = value % rate;
        supply = currentSupply;
        token.mint(_to, amount);
    }
}
