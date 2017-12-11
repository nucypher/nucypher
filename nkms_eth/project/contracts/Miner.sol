pragma solidity ^0.4.0;


import "./MineableToken.sol";
import "./lib/ExponentMath.sol";
import "./zeppelin/math/SafeMath.sol";


/**
* @notice Contract for minting tokens
**/
contract Miner {
    using SafeMath for uint256;

    MineableToken token;
    uint256 public miningCoefficient;

    /**
    * @notice The Miner constructor sets address of token contract and coefficients for mining
    * @dev Formula for mining
    (futureSupply - currentSupply) * (lockedBlocks * lockedValue / totalLockedValue / k)
    * @param _token Token contract
    * @param _miningCoefficient Mining coefficient (k)
    **/
    function Miner(MineableToken _token, uint256 _miningCoefficient) {
        require(address(_token) != 0x0 && _miningCoefficient != 0);
        token = _token;
        miningCoefficient = _miningCoefficient;
    }

//    /**
//    * @dev Check reward.
//    * @param _lockedBlocks The amount of blocks during which tokens were locked.
//    * @return Reward is empty or not
//    **/
//    // TODO complete
//    function isEmptyReward(uint256 _lockedBlocks)
//        constant returns (bool)
//    {
//        return token.totalSupply() == token.futureSupply() ||
//            (token.futureSupply().mul(_lockedBlocks).div(miningCoefficient) -
//            token.totalSupply().mul(_lockedBlocks).div(miningCoefficient)) == 0;
//    }

    /**
    * @notice Function to mint tokens for sender
    * @param _to The address that will receive the minted tokens.
    * @param _lockedValue The amount of tokens that were locked by user.
    * @param _totalLockedValue The amount of tokens that were locked by all users.
    * @param _lockedBlocks The amount of blocks during which tokens were locked.
    * @param _decimals The amount of locked tokens and blocks in decimals.
    * @return Amount of minted tokens.
    */
    function mint(
        address _to,
        uint256 _lockedValue,
        uint256 _totalLockedValue,
        uint256 _lockedBlocks,
        uint256 _decimals
    )
        internal returns (uint256 amount, uint256 decimals)
    {
        //futureSupply * lockedBlocks * lockedValue / (totalLockedValue * k) -
        //currentSupply * lockedBlocks * lockedValue / (totalLockedValue * k)
        uint256 denominator = _totalLockedValue.mul(miningCoefficient);
        uint256 maxValue = token.futureSupply().mul(_lockedBlocks).mul(_lockedValue).div(denominator);
        uint256 value = token.totalSupply().mul(_lockedBlocks).mul(_lockedValue).div(denominator);
        amount = maxValue.sub(value);
        token.mint(_to, amount);
    }
}
