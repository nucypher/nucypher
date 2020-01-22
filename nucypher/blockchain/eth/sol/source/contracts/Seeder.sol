pragma solidity ^0.6.1;


import "zeppelin/ownership/Ownable.sol";


/**
* @notice Contract holds references to seed
* node interface information for bootstrapping the network.
*/
contract Seeder is Ownable {

    struct SeedInfo {
        string ip;
        uint16 port;
    }


    mapping (address => SeedInfo) public seeds;
    address[] public seedArray;

    /**
    * @param _maxSeeds The quantity of maximum seed nodes the contract can store
    */
    constructor(uint256 _maxSeeds) public {
        seedArray = new address[](_maxSeeds);
    }

    /**
    * @notice Returns the length of the seed nodes array
    */
    function getSeedArrayLength()
        external view returns (uint256)
    {
        return seedArray.length;
    }

    /**
    * @notice Write a new seed address and interface info to contract storage
    * @param _ip IPv4 address of the seed node
    * @param _port TCP port of the seed node
    */
    function enroll(address _seed, string calldata _ip, uint16 _port) external onlyOwner {
        seeds[_seed] = SeedInfo(_ip, _port);

        uint256 i = 0;
        for (; i < seedArray.length; i++) {
            address currentSeed = seedArray[i];
            if (currentSeed == address(0)) {
                seedArray[i] = _seed;
                break;
            } else if (currentSeed == _seed) {
                break;
            }
        }
        require(i < seedArray.length,
            'Not enough slots to enroll a new seed node');
    }

    /**
    * @notice Seed updates itself.
    * @param _ip Updated IPv4 address of the existing seed node
    * @param _port Updated TCP port of the existing seed node
    */
    function refresh(string calldata _ip, uint16 _port) external {
        SeedInfo storage seed = seeds[msg.sender];
        require(seed.port != 0);
        seed.ip = _ip;
        seed.port = _port;
    }
}
