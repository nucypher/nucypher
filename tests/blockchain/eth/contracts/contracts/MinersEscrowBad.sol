pragma solidity ^0.4.23;


import "contracts/MinersEscrow.sol";
import "contracts/NuCypherToken.sol";


/**
* @notice Contract for using in MinersEscrow tests
**/
contract MinersEscrowBad is MinersEscrow {

    constructor(
        NuCypherToken _token,
        uint256 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint256 _awardedPeriods,
        uint256 _minReleasePeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens
    )
        public
        MinersEscrow(
            _token,
            _hoursPerPeriod,
            _miningCoefficient,
            _lockedPeriodsCoefficient,
            _awardedPeriods,
            _minReleasePeriods,
            _minAllowableLockedTokens,
            _maxAllowableLockedTokens
        )
    {
    }

    function getStakeInfo(address, uint256) public view returns (uint256, uint256, uint256, uint256)
    {
    }

}