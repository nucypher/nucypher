pragma solidity ^0.4.25;


import "contracts/Seeder.sol";
import "./Fixtures.sol";


/**
* @notice Tests invariants of array of seeds
**/
contract SeederTest is Seeder {

    constructor() public Seeder(2) {
        seeds[Fixtures.addressList(1)] = SeedInfo("host1", 1);
        seedArray[0] = Fixtures.addressList(1);
        owner = Fixtures.echidnaCaller();
    }

    function echidnaArrayTest() public view returns (bool) {
        return seedArray.length == 2;
    }

    function echidnaSeedTest() public view returns (bool) {
        return seedArray[0] == Fixtures.addressList(1);
    }

}
