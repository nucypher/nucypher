pragma solidity ^0.4.15;


import "../zeppelin/ownership/Ownable.sol";


/**
* @dev Based on https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/UpgradableContractProxyOLD.sol
* TODO When python TestRPC will have Byzantium hard fork then should use https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/UpgradableContractProxy.sol
* @notice Proxying requests to other contracts.
* Client should use abi of real contract and address of this contract
**/
contract Dispatcher is Ownable {

    // Contracts at the target must reserve the first location in storage for this address as
    // they will be called through this contract. This contract masquerades as the implementation to create a common
    // location for storage of vars.
    address public target;

    /**
    * @param _target Target contract address
    **/
    function Dispatcher(address _target) public {
        target = _target;
    }

    /**
    * @param _target New target contract address
    **/
    function setTarget(address _target) onlyOwner {
        target = _target;
    }

    /**
    * @dev Fallback function send all requests to the target contract.
    * If contract not exists then result will be unpredictable (see DELEGATECALL)
    **/
    function () public payable {
        assert(target != 0x0);

        address upgradableContractMem = target;
        uint32 size = 32;

        assembly {
            let freeMemAddress := mload(0x40)
            mstore(0x40, add(freeMemAddress, calldatasize))
            calldatacopy(freeMemAddress, 0x0, calldatasize)

//            switch delegatecall(gas, upgradableContractMem, freeMemAddress, calldatasize, 0, 0)
            switch delegatecall(gas, upgradableContractMem, freeMemAddress, calldatasize, 0, size)
                case 0 {
                    revert(0x0, 0)
                }
                default {
//                    returndatacopy(0x0, 0x0, returndatasize)
                    return(0x0, size)
                }
        }
    }

}
