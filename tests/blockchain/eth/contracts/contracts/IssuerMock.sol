pragma solidity ^0.4.18;


import "contracts/Issuer.sol";
import "contracts/NuCypherKMSToken.sol";


/**
* @dev Contract for testing internal methods in Issuer contract
**/
contract IssuerMock is Issuer {

    constructor(
        NuCypherKMSToken _token,
        uint256 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint256 _awardedPeriods
    )
        public
        Issuer(
            _token,
            _hoursPerPeriod,
            _miningCoefficient,
            _lockedPeriodsCoefficient,
            _awardedPeriods
        )
    {
    }

    function testMint(
        uint256 _period,
        uint256 _lockedValue,
        uint256 _totalLockedValue,
        uint256 _allLockedPeriods,
        uint256 _decimals
    )
        public returns (uint256 amount, uint256 decimals)
    {
        (amount, decimals) = mint(
            _period,
            _lockedValue,
            _totalLockedValue,
            _allLockedPeriods,
            _decimals);
        token.transfer(msg.sender, amount);
    }

}
