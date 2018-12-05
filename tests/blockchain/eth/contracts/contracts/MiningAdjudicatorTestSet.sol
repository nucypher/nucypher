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

    function setMinerInfo(address _miner, uint256 _amount) public {
        minerInfo[_miner].value = _amount;
    }

    // TODO tests for _investigator and _reward fields
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


/**
* @notice Upgrade to this contract must lead to fail
**/
contract MiningAdjudicatorBad is Upgradeable {

    MinersEscrow public escrow;
    mapping (bytes32 => bool) public evaluatedCFrags;
    SignatureVerifier.HashAlgorithm public hashAlgorithm;

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
        SignatureVerifier.HashAlgorithm _hashAlgorithm
    )
        public MiningAdjudicator(_escrow, _hashAlgorithm)
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