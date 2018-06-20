pragma solidity ^0.4.24;


import "proxy/Upgradeable.sol";


/**
* @notice Contract for using in Issuer tests
**/
contract IssuerBad is Upgradeable {

    address public token;
    uint256 public miningCoefficient;
    uint256 public lockedPeriodsCoefficient;
    uint32 public secondsPerPeriod;
    uint16 public rewardedPeriods;

    uint16 public lastMintedPeriod;
//    uint256 public currentSupply1;
    uint256 public currentSupply2;

    function verifyState(address) public {}
    function finishUpgrade(address) public {}

}