pragma solidity ^0.4.25;


import "contracts/NuCypherToken.sol";
import "contracts/MinersEscrow.sol";
import "contracts/PolicyManager.sol";
import "contracts/UserEscrowProxy.sol";
import "contracts/UserEscrow.sol";


library Fixtures {

    // TODO https://github.com/trailofbits/echidna/issues/147
//    function contractAddress() internal pure returns (address) {
//        return 0x00a329c0648769A73afAc7F9381E08FB43dBEA72;
//    }

    function echidnaCaller() internal pure returns (address) {
        return 0x00a329C0648769a73afAC7F9381e08fb43DBEA70;
    }

    function addressList(uint256 _index) internal pure returns (address) {
        if (_index == 1) {
            return 0x1;
        } else if (_index == 2) {
            return 0x2;
        } else if (_index == 3) {
            return 0x3;
        }
        revert();
    }

    function address2() internal pure returns (address) {
        return 0x2;
    }

    function address3() internal pure returns (address) {
        return 0x3;
    }

    function createDefaultToken() internal returns (NuCypherToken) {
        return new NuCypherToken(10000000);
    }

    function createDefaultMinersEscrow(NuCypherToken _token) internal returns (MinersEscrow) {
        return new DefaultMinersEscrow(_token);
    }

    function createDefaultMinersEscrow() internal returns (MinersEscrow) {
        return createDefaultMinersEscrow(createDefaultToken());
    }

    function createDefaultPolicyManager(MinersEscrow _escrow) internal returns (PolicyManager) {
        return new PolicyManager(_escrow);
    }

    function createDefaultPolicyManager() internal returns (PolicyManager) {
        return new PolicyManager(createDefaultMinersEscrow());
    }

    function createDefaultUserEscrowLinker(NuCypherToken _token, MinersEscrow _escrow, PolicyManager _policyManager)
        internal returns (UserEscrowLibraryLinker)
    {
        UserEscrowProxy userEscrowProxy = new UserEscrowProxy(_token, _escrow, _policyManager);
        return new UserEscrowLibraryLinker(userEscrowProxy, bytes32(1));
    }

    function createDefaultUserEscrow(NuCypherToken _token, MinersEscrow _escrow, PolicyManager _policyManager)
        internal returns (UserEscrow)
    {
        UserEscrowLibraryLinker userEscrowLinker = createDefaultUserEscrowLinker(_token, _escrow, _policyManager);
        return new UserEscrow(userEscrowLinker, _token);
    }

}


contract DefaultMinersEscrow is MinersEscrow {

    constructor(NuCypherToken _token) public MinersEscrow(_token, 1, 4 * 2 * 10 ** 7, 4, 4, 2, 0, 100000) {
    }

    function getCurrentPeriod() public view returns (uint16) {
        return 10;
    }

}
