pragma solidity ^0.5.3;


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
        require(_target != address(0));
        target = _target;
        secretHash = _newSecretHash;
        (bool callSuccess,) = target.delegatecall(abi.encodeWithSignature("finishUpgrade(address)", target));
        require(callSuccess);
        emit Upgraded(address(0), _target, msg.sender);
    }

    /**
    * @notice Verify new contract storage and upgrade target
    * @param _target New target contract address
    * @param _secret Secret for proof of contract owning
    * @param _newSecretHash New secret hash (keccak256)
    **/
    function upgrade(address _target, bytes memory _secret, bytes32 _newSecretHash) public onlyOwner {
        require(keccak256(_secret) == secretHash && _newSecretHash != secretHash);
        verifyState(_target);
        verifyUpgradeableState(target, _target);
        previousTarget = target;
        target = _target;
        secretHash = _newSecretHash;
        (bool callSuccess,) = target.delegatecall(abi.encodeWithSignature("finishUpgrade(address)", target));
        require(callSuccess);
        emit Upgraded(previousTarget, _target, msg.sender);
    }

    function verifyState(address _testTarget) public onlyOwner {
        //checks equivalence accessing target through new contract and current storage
        require(address(uint160(delegateGet(_testTarget, "owner()"))) == owner());
        require(address(uint160(delegateGet(_testTarget, "target()"))) == target);
        require(address(uint160(delegateGet(_testTarget, "previousTarget()"))) == previousTarget);
        require(bytes32(delegateGet(_testTarget, "secretHash()")) == secretHash);
    }

    /**
    * @notice Rollback to previous target
    * @dev Test storage carefully before upgrade again after rollback
    * @param _secret Secret for proof of contract owning
    * @param _newSecretHash New secret hash (keccak256)
    **/
    function rollback(bytes memory _secret, bytes32 _newSecretHash) public onlyOwner {
        require(previousTarget != address(0));
        require(keccak256(_secret) == secretHash && _newSecretHash != secretHash);
        emit RolledBack(target, previousTarget, msg.sender);
        verifyUpgradeableState(previousTarget, target);
        target = previousTarget;
        previousTarget = address(0);
        secretHash = _newSecretHash;
        (bool callSuccess,) = target.delegatecall(abi.encodeWithSignature("finishUpgrade(address)", target));
        require(callSuccess);
    }

    /**
    * @dev Call verifyState method for Upgradeable contract
    **/
    function verifyUpgradeableState(address _from, address _to) internal {
        (bool callSuccess,) = _from.delegatecall(abi.encodeWithSignature("verifyState(address)", _to));
        require(callSuccess);
    }

    function finishUpgrade(address) public {}

    /**
    * @dev Fallback function send all requests to the target contract.
    * If contract not exists then result will be unpredictable (see DELEGATECALL)
    **/
    function () external payable {
        assert(target != address(0));
        (bool callSuccess,) = target.delegatecall(msg.data);
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
