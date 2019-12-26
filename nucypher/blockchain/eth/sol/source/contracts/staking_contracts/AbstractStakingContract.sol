pragma solidity ^0.5.3;


import "zeppelin/ownership/Ownable.sol";
import "zeppelin/utils/Address.sol";


/**
* @notice Router for accessing interface contract
*/
contract StakingInterfaceRouter is Ownable {
    using Address for address;

    address public target;
    bytes32 public secretHash;

    /**
    * @param _target Address of the interface contract
    * @param _newSecretHash Secret hash (keccak256)
    */
    constructor(address _target, bytes32 _newSecretHash) public {
        require(_target.isContract());
        target = _target;
        secretHash = _newSecretHash;
    }

    /**
    * @notice Upgrade interface
    * @param _target New contract address
    * @param _secret Secret for proof of contract owning
    * @param _newSecretHash New secret hash (keccak256)
    */
    function upgrade(address _target, bytes memory _secret, bytes32 _newSecretHash) public onlyOwner {
        require(_target.isContract());
        require(keccak256(_secret) == secretHash && _newSecretHash != secretHash);
        target = _target;
        secretHash = _newSecretHash;
    }

}


/**
* @notice Base class for any staking contract
* @dev Implement `isFallbackAllowed()` or override fallback function
*/
contract AbstractStakingContract {
    using Address for address;

    StakingInterfaceRouter public router;

    /**
    * @param _router Interface router contract address
    */
    constructor(StakingInterfaceRouter _router) public {
        // check that the input address is contract
        require(_router.target().isContract());
        router = _router;
    }

    /**
    * @dev Checks permission for calling fallback function
    */
    function isFallbackAllowed() public returns (bool);

    /**
    * @dev Function sends all requests to the target contract
    */
    function () external payable {
        require(isFallbackAllowed());
        address target = router.target();
        require(target.isContract());
        // execute requested function from target contract
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
