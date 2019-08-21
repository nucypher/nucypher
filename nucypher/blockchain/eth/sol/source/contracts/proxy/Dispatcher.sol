pragma solidity ^0.5.3;


import "./Upgradeable.sol";
import "zeppelin/utils/Address.sol";


/**
* @notice Proxying requests to other contracts.
* Client should use ABI of real contract and address of this contract
**/
contract Dispatcher is Upgradeable {
    using Address for address;

    event Upgraded(address indexed from, address indexed to, address owner);
    event RolledBack(address indexed from, address indexed to, address owner);

    /**
    * @dev Set upgrading status before and after operations
    **/
    modifier upgrading()
    {
        isUpgrade = UPGRADE_TRUE;
        _;
        isUpgrade = UPGRADE_FALSE;
    }

    /**
    * @param _target Target contract address
    * @param _newSecretHash Secret hash (keccak256)
    **/
    constructor(address _target, bytes32 _newSecretHash) public upgrading {
        require(_target.isContract());
        // Checks that target contract inherits Dispatcher state
        verifyState(_target);
        // `verifyState` must work with its contract
        verifyUpgradeableState(_target, _target);
        target = _target;
        secretHash = _newSecretHash;
        finishUpgrade();
        emit Upgraded(address(0), _target, msg.sender);
    }

    /**
    * @notice Verify new contract storage and upgrade target
    * @param _target New target contract address
    * @param _secret Secret for proof of contract owning
    * @param _newSecretHash New secret hash (keccak256)
    **/
    function upgrade(address _target, bytes memory _secret, bytes32 _newSecretHash) public onlyOwner upgrading {
        require(_target.isContract());
        require(keccak256(_secret) == secretHash && _newSecretHash != secretHash);
        // Checks that target contract has "correct" (as much as possible) state layout
        verifyState(_target);
        //`verifyState` must work with its contract
        verifyUpgradeableState(_target, _target);
        if (target.isContract()) {
            verifyUpgradeableState(target, _target);
        }
        previousTarget = target;
        target = _target;
        secretHash = _newSecretHash;
        finishUpgrade();
        emit Upgraded(previousTarget, _target, msg.sender);
    }

    /**
    * @notice Rollback to previous target
    * @dev Test storage carefully before upgrade again after rollback
    * @param _secret Secret for proof of contract owning
    * @param _newSecretHash New secret hash (keccak256)
    **/
    function rollback(bytes memory _secret, bytes32 _newSecretHash) public onlyOwner upgrading {
        require(previousTarget.isContract());
        require(keccak256(_secret) == secretHash && _newSecretHash != secretHash);
        emit RolledBack(target, previousTarget, msg.sender);
        // should be always true because layout previousTarget -> target was already checked
        // but `verifyState` is not 100% accurate so check again
        verifyState(previousTarget);
        if (target.isContract()) {
            verifyUpgradeableState(previousTarget, target);
        }
        target = previousTarget;
        previousTarget = address(0);
        secretHash = _newSecretHash;
        finishUpgrade();
    }

    /**
    * @dev Call verifyState method for Upgradeable contract
    **/
    function verifyUpgradeableState(address _from, address _to) private {
        (bool callSuccess,) = _from.delegatecall(abi.encodeWithSignature("verifyState(address)", _to));
        require(callSuccess);
    }

    /**
    * @dev Call finishUpgrade method from the Upgradeable contract
    **/
    function finishUpgrade() private {
        (bool callSuccess,) = target.delegatecall(abi.encodeWithSignature("finishUpgrade(address)", target));
        require(callSuccess);
    }

    function verifyState(address _testTarget) public onlyWhileUpgrading {
        //checks equivalence accessing state through new contract and current storage
        require(address(uint160(delegateGet(_testTarget, "owner()"))) == owner());
        require(address(uint160(delegateGet(_testTarget, "target()"))) == target);
        require(address(uint160(delegateGet(_testTarget, "previousTarget()"))) == previousTarget);
        require(bytes32(delegateGet(_testTarget, "secretHash()")) == secretHash);
        require(uint8(delegateGet(_testTarget, "isUpgrade()")) == isUpgrade);
    }

    /**
    * @dev Override function using empty code because no reason to call this function in Dispatcher
    **/
    function finishUpgrade(address) public {}

    /**
    * @dev Fallback function send all requests to the target contract
    **/
    function () external payable {
        assert(target.isContract());
        // execute requested function from target contract using storage of the dispatcher
        (bool callSuccess,) = target.delegatecall(msg.data);
        if (callSuccess) {
            // copy result of the request to the return data
            // we can use the second return value from `delegatecall` (bytes memory)
            // but it will consume a little more gas
            assembly {
                returndatacopy(0x0, 0x0, returndatasize)
                return(0x0, returndatasize)
            }
        } else {
            revert();
        }
    }

}
