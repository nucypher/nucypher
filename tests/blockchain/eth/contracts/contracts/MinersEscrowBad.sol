pragma solidity ^0.4.24;


import "contracts/MinersEscrow.sol";
import "contracts/NuCypherToken.sol";


/**
* @notice Contract for using in MinersEscrow tests
**/
contract MinersEscrowBad is MinersEscrow {

    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint16 _rewardedPeriods,
        uint16 _minReleasePeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens
    )
        public
        MinersEscrow(
            _token,
            _hoursPerPeriod,
            _miningCoefficient,
            _lockedPeriodsCoefficient,
            _rewardedPeriods,
            _minReleasePeriods,
            _minAllowableLockedTokens,
            _maxAllowableLockedTokens
        )
    {
    }

    function getStakeInfo(address, uint256) public view returns (uint16, uint16, uint16, uint256)
    {
    }

}