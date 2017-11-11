pragma solidity ^0.4.0;


import "./MineableToken.sol";
import "./ExponentMath.sol";
import "zeppelin-solidity/contracts/math/SafeMath.sol";


/**
* @notice Contract for minting tokens
**/
//TODO tests
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
    * @notice Function to mint tokens for sender
    * @param _lockedValue The amount of tokens that were locked.
    * @param _lockedBlocks The amount of blocks during which tokens were locked.
    * @return Amount of minted tokens.
    */
    function mint(uint256 _lockedValue, uint256 _lockedBlocks)
        internal returns (uint256)
    {
        //TODO save decimals
        uint256 newMintedPoint = lastMintedPoint.add(_lockedValue.mul(_lockedBlocks).div(rate));
        if (newMintedPoint == lastMintedPoint) {
            return 0;
        }
        lastMintedPoint = newMintedPoint;
        uint256 currentSupply = ExponentMath.exponentialFunction(
            lastMintedPoint, maxValue, fractions, multiplicator, ITERATIONS);
        uint256 amount = currentSupply.sub(supply);
        supply = currentSupply;
        token.mint(msg.sender, amount);
        return amount;
    }
}
