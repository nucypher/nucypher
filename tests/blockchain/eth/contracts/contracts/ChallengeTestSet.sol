pragma solidity ^0.4.25;


/**
* @notice Contract for testing the ChallengeOverseer contract
**/
contract MinersEscrowForChallengeOverseerMock {

    struct MinerInfo {
        uint256 value;
        uint16 stubValue1;
        uint16 stubValue2;
        uint16 stubValue3;
    }

    mapping (address => MinerInfo) public minerInfo;

    function setMinerInfo(address _miner, uint256 _amount) public {
        minerInfo[_miner].value = _amount;
    }

    function slashMiner(
        address _miner,
        uint256 _penalty,
        address _investigator,
        uint256 _reward
    )
        public
    {
        minerInfo[_miner].value -= _penalty;
    }

}
