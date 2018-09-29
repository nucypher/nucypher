pragma solidity ^0.4.23;


import "./Upgradeable.sol";


/**
* @dev Based on https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/contracts/UpgradableContractProxy.sol
* @notice Proxying requests to other contracts.
* Client should use ABI of real contract and address of this contract
**/
contract Dispatcher is Upgradeable {

    event Upgraded(address indexed from, address indexed to, address owner);
    event RolledBack(address indexed from, address indexed to, address owner);

    /**
    * @param _target Target contract address
    * @param _newSecretHash Secret hash (keccak256)
    **/
    constructor(address _target, bytes32 _newSecretHash) public {
        require(_target != 0x0);
        target = _target;
        secretHash = _newSecretHash;
        require(target.delegatecall(bytes4(keccak256("finishUpgrade(address)")), target));
        emit Upgraded(0x0, _target, msg.sender);
    }

    /**
    * @notice Verify new contract storage and upgrade target
    * @param _target New target contract address
    * @param _secret Secret for proof of contract owning
    * @param _newSecretHash New secret hash (keccak256)
    **/
    function upgrade(address _target, bytes _secret, bytes32 _newSecretHash) public onlyOwner {
        require(keccak256(_secret) == secretHash && _newSecretHash != secretHash);
        verifyState(_target);
        verifyUpgradeableState(target, _target);
        previousTarget = target;
        target = _target;
        secretHash = _newSecretHash;
        require(target.delegatecall(bytes4(keccak256("finishUpgrade(address)")), target));
        emit Upgraded(previousTarget, _target, msg.sender);
    }

    function verifyState(address _testTarget) public onlyOwner {
        //checks equivalence accessing target through new contract and current storage
        require(address(delegateGet(_testTarget, "owner()")) == owner);
        require(address(delegateGet(_testTarget, "target()")) == target);
        require(address(delegateGet(_testTarget, "previousTarget()")) == previousTarget);
        require(delegateGet(_testTarget, "secretHash()") == secretHash);
    }

    /**
    * @notice Rollback to previous target
    * @dev Test storage carefully before upgrade again after rollback
    * @param _secret Secret for proof of contract owning
    * @param _newSecretHash New secret hash (keccak256)
    **/
    function rollback(bytes _secret, bytes32 _newSecretHash) public onlyOwner {
        require(previousTarget != 0x0);
        require(keccak256(_secret) == secretHash && _newSecretHash != secretHash);
        emit RolledBack(target, previousTarget, msg.sender);
        verifyUpgradeableState(previousTarget, target);
        target = previousTarget;
        previousTarget = 0x0;
        secretHash = _newSecretHash;
        require(target.delegatecall(bytes4(keccak256("finishUpgrade(address)")), target));
    }

    /**
    * @dev Call verifyState method for Upgradeable contract
    **/
    function verifyUpgradeableState(address _from, address _to) internal {
        require(_from.delegatecall(bytes4(keccak256("verifyState(address)")), _to));
    }

    function finishUpgrade(address) public {}

    /**
    * @dev Fallback function send all requests to the target contract.
    * If contract not exists then result will be unpredictable (see DELEGATECALL)
    **/
    function () public payable {
        assert(target != 0x0);
        bool callSuccess = target.delegatecall(msg.data);
        if (callSuccess) {
            assembly {
                returndatacopy(0x0, 0x0, returndatasize)
                return(0x0, returndatasize)
            }
        } else {
            revert();
        }
    }

}
