pragma solidity ^0.4.18;


import "contracts/MinersEscrow.sol";
import "contracts/NuCypherKMSToken.sol";


/**
* @notice Contract for using in MinersEscrow tests
**/
contract MinersEscrowBad is MinersEscrow {

    constructor(
        NuCypherKMSToken _token,
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

    function getMinerInfo(MinersEscrow.MinerInfoField, address, uint256)
        public view returns (bytes32)
    {
    }

}