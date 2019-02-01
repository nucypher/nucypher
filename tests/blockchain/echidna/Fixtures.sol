pragma solidity ^0.4.25;


import "contracts/NuCypherToken.sol";
import "contracts/MinersEscrow.sol";
import "contracts/PolicyManager.sol";
import "contracts/UserEscrowProxy.sol";
import "contracts/UserEscrow.sol";


/**
* @notice Constants from Echidna configuration and methods for contracts creation
**/
library Fixtures {

    /**
    * @notice Address of the test contract
    **/
    // TODO https://github.com/trailofbits/echidna/issues/147
//    function contractAddress() internal pure returns (address) {
//        return 0x00a329c0648769A73afAc7F9381E08FB43dBEA72;
//    }

    /**
    * @notice Address of the caller in tests
    **/
    function echidnaCaller() internal pure returns (address) {
        return 0x00a329C0648769a73afAC7F9381e08fb43DBEA70;
    }

    /**
    * @notice List of addresses used in tests
    **/
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

    /**
    * @notice Creates default token contract
    **/
    function createDefaultToken() internal returns (NuCypherToken) {
        return new NuCypherToken(10000000);
    }

    /**
    * @notice Creates default MinersEscrow contract using specified token address
    **/
    function createDefaultMinersEscrow(NuCypherToken _token) internal returns (MinersEscrow) {
        return new DefaultMinersEscrow(_token);
    }

    /**
    * @notice Creates default MinersEscrow contract using default token
    **/
    function createDefaultMinersEscrow() internal returns (MinersEscrow) {
        return createDefaultMinersEscrow(createDefaultToken());
    }

    /**
    * @notice Creates default PolicyManager contract using specified MinersEscrow contract
    **/
    function createDefaultPolicyManager(MinersEscrow _escrow) internal returns (PolicyManager) {
        return new PolicyManager(_escrow);
    }

    /**
    * @notice Creates default PolicyManager contract using default MinersEscrow contract
    **/
    function createDefaultPolicyManager() internal returns (PolicyManager) {
        return new PolicyManager(createDefaultMinersEscrow());
    }

    /**
    * @notice Creates default UserEscrowLibraryLinker and UserEscrowProxy contracts
    **/
    function createDefaultUserEscrowLinker(NuCypherToken _token, MinersEscrow _escrow, PolicyManager _policyManager)
        internal returns (UserEscrowLibraryLinker)
    {
        UserEscrowProxy userEscrowProxy = new UserEscrowProxy(_token, _escrow, _policyManager);
        return new UserEscrowLibraryLinker(userEscrowProxy, bytes32(1));
    }

    /**
    * @notice Creates default UserEscrow contract
    **/
    function createDefaultUserEscrow(NuCypherToken _token, MinersEscrow _escrow, PolicyManager _policyManager)
        internal returns (UserEscrow)
    {
        UserEscrowLibraryLinker userEscrowLinker = createDefaultUserEscrowLinker(_token, _escrow, _policyManager);
        return new UserEscrow(userEscrowLinker, _token);
    }

}


/**
* @notice Default MinersEscrow contract
**/
contract DefaultMinersEscrow is MinersEscrow {

    constructor(NuCypherToken _token) public MinersEscrow(_token, 1, 4 * 2 * 10 ** 7, 4, 4, 2, 0, 100000) {
    }

    function getCurrentPeriod() public view returns (uint16) {
        return 10;
    }

}
