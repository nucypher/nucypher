pragma solidity ^0.4.0;


import "./MineableToken.sol";
import "./zeppelin/math/SafeMath.sol";


/**
* @notice Contract for minting tokens
**/
contract Miner {
    using SafeMath for uint256;

    MineableToken token;
    uint256 public miningCoefficient;
    uint256 public lockedBlocksCoefficient;
    uint256 public awardedLockedBlocks;

    /**
    * @notice The Miner constructor sets address of token contract and coefficients for mining
    * @dev Formula for mining
    (futureSupply - currentSupply) * (lockedBlocks * lockedValue / totalLockedValue) * (k1 + allLockedBlocks) / k2
    if allLockedBlocks > awardedLockedBlocks then allLockedBlocks = awardedLockedBlocks
    * @param _token Token contract
    * @param _miningCoefficient Mining coefficient (k2)
    * @param _lockedBlocksCoefficient Locked blocks coefficient (k1)
    * @param _awardedLockedBlocks Max blocks that will be additionally awarded
    **/
    function Miner(
        MineableToken _token,
        uint256 _miningCoefficient,
        uint256 _lockedBlocksCoefficient,
        uint256 _awardedLockedBlocks
    ) {
        require(address(_token) != 0x0 &&
            _miningCoefficient != 0 &&
            _lockedBlocksCoefficient != 0 &&
            _awardedLockedBlocks != 0);
        token = _token;
        miningCoefficient = _miningCoefficient;
        lockedBlocksCoefficient = _lockedBlocksCoefficient;
        awardedLockedBlocks = _awardedLockedBlocks;
    }

    /**
    * @notice Function to mint tokens for sender
    * @param _to The address that will receive the minted tokens.
    * @param _lockedValue The amount of tokens that were locked by user.
    * @param _totalLockedValue The amount of tokens that were locked by all users.
    * @param _currentLockedBlocks The current amount of blocks during which tokens were locked.
    * @param _allLockedBlocks The max amount of blocks during which tokens were locked.
    * @param _decimals The amount of locked tokens and blocks in decimals.
    * @return Amount of minted tokens.
    */
    function mint(
        address _to,
        uint256 _lockedValue,
        uint256 _totalLockedValue,
        uint256 _currentLockedBlocks,
        uint256 _allLockedBlocks,
        uint256 _decimals
    )
        internal returns (uint256 amount, uint256 decimals)
    {
        //futureSupply * currentLockedBlocks * lockedValue * (k1 + allLockedBlocks) / (totalLockedValue * k2) -
        //currentSupply * currentLockedBlocks * lockedValue * (k1 + allLockedBlocks) / (totalLockedValue * k2)
        var allLockedBlocks = (_allLockedBlocks <= awardedLockedBlocks ?
            _allLockedBlocks : awardedLockedBlocks).add(lockedBlocksCoefficient);
        var denominator = _totalLockedValue.mul(miningCoefficient);
        var maxValue = token.futureSupply()
            .mul(_currentLockedBlocks)
            .mul(_lockedValue)
//            .mul(allLockedBlocks)
            .div(denominator);
        var value = token.totalSupply()
            .mul(_currentLockedBlocks)
            .mul(_lockedValue)
//            .mul(allLockedBlocks)
            .div(denominator);
        amount = maxValue.sub(value);
        token.mint(_to, amount);
    }
}
