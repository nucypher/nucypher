pragma solidity ^0.4.18;


import "proxy/Upgradeable.sol";


/**
* @notice Contract for using in Issuer tests
**/
contract IssuerBad is Upgradeable {

    address public token;
    uint256 public miningCoefficient;
    uint256 public secondsPerPeriod;
    uint256 public lockedPeriodsCoefficient;
    uint256 public awardedPeriods;

    uint256 public lastMintedPeriod;
    mapping (byte => uint256) public totalSupply;
//    byte public currentIndex;
    uint256 public futureSupply;

    function verifyState(address) public {}
    function finishUpgrade(address) public {}

}