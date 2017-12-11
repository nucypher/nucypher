pragma solidity ^0.4.11;


import "contracts/Miner.sol";
import "contracts/MineableToken.sol";


/**
* @dev Contract for testing internal methods in Miner contract
**/
contract MinerTest is Miner {

    function MinerTest(
        MineableToken _token,
        uint256 _miningCoefficient
    )
        Miner(_token, _miningCoefficient)
    {
    }

    function testMint(
        address _to,
        uint256 _lockedValue,
        uint256 _totalLockedValue,
        uint256 _lockedBlocks,
        uint256 _decimals
    )
        public returns (uint256 amount, uint256 decimals)
    {
        return mint(_to, _lockedValue, _totalLockedValue, _lockedBlocks, _decimals);
    }

}
