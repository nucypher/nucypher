pragma solidity ^0.4.25;


/**
* @notice Contract for testing the ChallengeOverseer contract
**/
contract MinersEscrowStub {

    mapping (address => uint256) public minerInfo;

    function setMinerInfo(address _miner, uint256 _amount) public {
        minerInfo[_miner] = _amount;
    }

    function getLockedTokens(address _miner)
        public view returns (uint256)
    {
        return minerInfo[_miner];
    }

    function slashMiner(address _miner, uint256 _amount) public {
        minerInfo[_miner] -= _amount;
    }

}