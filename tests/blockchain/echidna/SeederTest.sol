pragma solidity ^0.4.25;


import "contracts/Seeder.sol";
import "./Constants.sol";


contract SeederTest is Seeder, Constants {

    constructor() public Seeder(2) {
        seeds[Constants.ADDRESS_1] = SeedInfo("host1", 1);
        seedArray[0] = Constants.ADDRESS_1;
        owner = Constants.ECHIDNA_CALLER;
    }

    function echidnaArrayTest() public view returns (bool) {
        return seedArray.length == 2;
    }

    function echidnaSeedTest() public view returns (bool) {
        return seeds[Constants.ADDRESS_1].port == 1 &&
            keccak256(abi.encodePacked(bytes(seeds[Constants.ADDRESS_1].ip))) == keccak256("host1") &&
            seedArray[0] == Constants.ADDRESS_1;
    }

}
