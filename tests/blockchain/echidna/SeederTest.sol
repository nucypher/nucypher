pragma solidity ^0.4.25;


import "contracts/Seeder.sol";


contract SeederTest is Seeder {

    address echidna_caller = 0x00a329C0648769a73afAC7F9381e08fb43DBEA70;

    constructor() public Seeder(2) {
        seeds[0x1] = SeedInfo("host1", 1);
        seedArray[0] = 0x1;
        owner = echidna_caller;
    }

    function echidnaArrayTest() public view returns (bool) {
        return seedArray.length == 2;
    }

    function echidnaSeedTest() public view returns (bool) {
        return seeds[0x1].port == 1 &&
            keccak256(abi.encodePacked(bytes(seeds[0x1].ip))) == keccak256("host1") &&
            seedArray[0] == 0x1;
    }

}
