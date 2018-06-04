pragma solidity ^0.4.23;


import "contracts/Issuer.sol";
import "contracts/NuCypherToken.sol";


/**
* @dev Contract for testing internal methods in Issuer contract
**/
contract IssuerMock is Issuer {

    constructor(
        NuCypherToken _token,
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
        uint256 _allLockedPeriods
    )
        public returns (uint256 amount)
    {
        amount = mint(
            _period,
            _lockedValue,
            _totalLockedValue,
            _allLockedPeriods);
        token.transfer(msg.sender, amount);
    }

}
