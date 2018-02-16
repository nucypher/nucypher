pragma solidity ^0.4.18;


import "./Upgradeable.sol";


/**
* @dev Based on https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/UpgradableContractProxyOLD.sol
* TODO When python TestRPC will have Byzantium hard fork then should use https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/UpgradableContractProxy.sol
* @notice Proxying requests to other contracts.
* Client should use ABI of real contract and address of this contract
**/
contract Dispatcher is Upgradeable {

    event TargetChanged(address from, address to, address admin);

    /**
    * @param _target Target contract address
    **/
    function Dispatcher(address _target) public {
        target = _target;
        require(target.delegatecall(bytes4(keccak256("finishUpgrade(address)")), target));
    }

    /**
    * @notice Verify new contract storage and upgrade target
    * @param _target New target contract address
    **/
    function upgrade(address _target) onlyOwner public {
        verifyState(_target);
        verifyUpgradeableState(target, _target);
        previousTarget = target;
        target = _target;
        require(target.delegatecall(bytes4(keccak256("finishUpgrade(address)")), target));
        TargetChanged(previousTarget, _target, owner);
    }

    function verifyState(address _testTarget) public constant {
        //checks equivalence accessing target through new contract and current storage
        require(address(delegateGet(_testTarget, "target()")) == target);
        require(address(delegateGet(_testTarget, "owner()")) == owner);
    }

    /**
    * @notice Rollback to previous target
    * @dev Test storage carefully before upgrade again after rollback
    **/
    function rollback() onlyOwner public {
        require(previousTarget != 0x0);
        verifyUpgradeableState(previousTarget, target);
        target = previousTarget;
        previousTarget = 0x0;
    }

    /**
    * @dev Call verifyState method for Upgradeable contract
    **/
    function verifyUpgradeableState(address _from, address _to) internal {
        require(_from.delegatecall(bytes4(keccak256("verifyState(address)")), _to));
    }

    function finishUpgrade(address _target) onlyOwner public {}

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
//                    return(0x0, returndatasize)
                    return(0x0, size)
                }
        }
    }

}
