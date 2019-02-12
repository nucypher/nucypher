pragma solidity ^0.4.25;


import "contracts/MiningAdjudicator.sol";
import "contracts/MinersEscrow.sol";
import "contracts/lib/SignatureVerifier.sol";
import "contracts/proxy/Upgradeable.sol";


/**
* @notice Contract for testing the MiningAdjudicator contract
**/
contract MinersEscrowForMiningAdjudicatorMock {

    struct MinerInfo {
        uint256 value;
        uint16 stubValue1;
        uint16 stubValue2;
        uint16 stubValue3;
    }

    mapping (address => MinerInfo) public minerInfo;
    mapping (address => uint256) public rewardInfo;

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
        rewardInfo[_investigator] += _reward;
    }

}


/**
* @notice Upgrade to this contract must lead to fail
**/
contract MiningAdjudicatorBad is Upgradeable {

    MinersEscrow public escrow;
    SignatureVerifier.HashAlgorithm public hashAlgorithm;
    uint256 public basePenalty;
    uint256 public penaltyHistoryCoefficient;
    uint256 public percentagePenalty;
    uint256 public rewardCoefficient;
    mapping (bytes32 => bool) public evaluatedCFrags;
    mapping (address => uint256) public penaltyHistory;

    function verifyState(address) public onlyOwner {}
    function finishUpgrade(address) public onlyOwner {}

}


/**
* @notice Contract for testing upgrading the MiningAdjudicator contract
**/
contract MiningAdjudicatorV2Mock is MiningAdjudicator {

    uint256 public valueToCheck;

    constructor(
        MinersEscrow _escrow,
        SignatureVerifier.HashAlgorithm _hashAlgorithm,
        uint256 _basePenalty,
        uint256 _percentagePenalty,
        uint256 _penaltyHistoryCoefficient,
        uint256 _rewardCoefficient
    )
        public
        MiningAdjudicator(
            _escrow,
            _hashAlgorithm,
            _basePenalty,
            _percentagePenalty,
            _penaltyHistoryCoefficient,
            _rewardCoefficient
        )
    {
    }

    function setValueToCheck(uint256 _valueToCheck) public {
        valueToCheck = _valueToCheck;
    }

    function verifyState(address _testTarget) public onlyOwner {
        super.verifyState(_testTarget);
        require(uint256(delegateGet(_testTarget, "valueToCheck()")) == valueToCheck);
    }
}