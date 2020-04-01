pragma solidity ^0.5.3;


import "zeppelin/ownership/Ownable.sol";
import "zeppelin/utils/Address.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";
import "contracts/staking_contracts/StakingInterface.sol";


/**
* @notice Router for accessing interface contract
*/
contract StakingInterfaceRouter is Ownable {
    BaseStakingInterface public target;
    bytes32 public secretHash;

    /**
    * @param _target Address of the interface contract
    * @param _newSecretHash Secret hash (keccak256)
    */
    constructor(BaseStakingInterface _target, bytes32 _newSecretHash) public {
        require(address(_target.token()) != address(0));
        target = _target;
        secretHash = _newSecretHash;
    }

    /**
    * @notice Upgrade interface
    * @param _target New contract address
    * @param _secret Secret for proof of contract owning
    * @param _newSecretHash New secret hash (keccak256)
    */
    function upgrade(BaseStakingInterface _target, bytes calldata _secret, bytes32 _newSecretHash) external onlyOwner {
        require(address(_target.token()) != address(0));
        require(keccak256(_secret) == secretHash && _newSecretHash != secretHash);
        target = _target;
        secretHash = _newSecretHash;
    }

}


/**
* @notice Base class for any staking contract
* @dev Implement `isFallbackAllowed()` or override fallback function
* Implement `withdrawTokens(uint256)` and `withdrawETH()` functions
*/
contract AbstractStakingContract {
    using Address for address;
    using Address for address payable;
    using SafeERC20 for NuCypherToken;

    StakingInterfaceRouter public router;
    NuCypherToken public token;

    /**
    * @param _router Interface router contract address
    */
    constructor(StakingInterfaceRouter _router) public {
        router = _router;
        token = _router.target().token();
        require(address(token) != address(0));
    }

    /**
    * @dev Checks permission for calling fallback function
    */
    function isFallbackAllowed() public returns (bool);

    /**
    * @dev Withdraw tokens from staking contract
    */
    function withdrawTokens(uint256 _value) public;

    /**
    * @dev Withdraw ETH from staking contract
    */
    function withdrawETH() public;

    /**
    * @dev Function sends all requests to the target contract
    */
    function () external payable {
        if (msg.data.length == 0) {
            return;
        }

        require(isFallbackAllowed());
        address target = address(router.target());
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
