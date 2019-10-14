pragma solidity ^0.5.3;


import "zeppelin/ownership/Ownable.sol";
import "zeppelin/utils/Address.sol";


/**
* @notice Links library with staking contracts
**/
contract UserEscrowLibraryLinker is Ownable {
    using Address for address;

    address public target;
    bytes32 public secretHash;

    /**
    * @param _target Address of the library contract
    * @param _newSecretHash Secret hash (keccak256)
    **/
    constructor(address _target, bytes32 _newSecretHash) public {
        require(_target.isContract());
        target = _target;
        secretHash = _newSecretHash;
    }

    /**
    * @notice Upgrade library
    * @param _target New contract address
    * @param _secret Secret for proof of contract owning
    * @param _newSecretHash New secret hash (keccak256)
    **/
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
**/
contract StakingContractBase {
    using Address for address;

    UserEscrowLibraryLinker public linker;

    /**
    * @param _linker StakerProxyLinker contract address
    **/
    constructor(UserEscrowLibraryLinker _linker) public {
        // check that the input address is contract
        require(_linker.target().isContract());
        linker = _linker;
    }

    /**
    * @dev Checks permission for calling fallback function
    **/
    function isFallbackAllowed() public returns (bool);

    /**
    * @dev Function sends all requests to the target proxy contract
    **/
    function () external payable {
        require(isFallbackAllowed());
        address proxy = linker.target();
        require(proxy.isContract());
        // execute requested function from target contract using storage of the dispatcher
        (bool callSuccess,) = proxy.delegatecall(msg.data);
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
