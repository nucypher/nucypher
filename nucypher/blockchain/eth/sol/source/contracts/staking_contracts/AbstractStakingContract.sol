// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;

import "zeppelin/ownership/Ownable.sol";
import "zeppelin/utils/Address.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";
import "contracts/staking_contracts/StakingInterface.sol";
import "zeppelin/proxy/Initializable.sol";


/**
* @notice Router for accessing interface contract
*/
contract StakingInterfaceRouter is Ownable {
    BaseStakingInterface public target;

    /**
    * @param _target Address of the interface contract
    */
    constructor(BaseStakingInterface _target) {
        require(address(_target.token()) != address(0));
        target = _target;
    }

    /**
    * @notice Upgrade interface
    * @param _target New contract address
    */
    function upgrade(BaseStakingInterface _target) external onlyOwner {
        require(address(_target.token()) != address(0));
        target = _target;
    }

}


/**
* @notice Internal base class for AbstractStakingContract and InitializableStakingContract
*/
abstract contract RawStakingContract {
    using Address for address;

    /**
    * @dev Returns address of StakingInterfaceRouter
    */
    function router() public view virtual returns (StakingInterfaceRouter);

    /**
    * @dev Checks permission for calling fallback function
    */
    function isFallbackAllowed() public virtual returns (bool);

    /**
    * @dev Withdraw tokens from staking contract
    */
    function withdrawTokens(uint256 _value) public virtual;

    /**
    * @dev Withdraw ETH from staking contract
    */
    function withdrawETH() public virtual;

    receive() external payable {}

    /**
    * @dev Function sends all requests to the target contract
    */
    fallback() external payable {
        require(isFallbackAllowed());
        address target = address(router().target());
        require(target.isContract());
        // execute requested function from target contract
        (bool callSuccess, ) = target.delegatecall(msg.data);
        if (callSuccess) {
            // copy result of the request to the return data
            // we can use the second return value from `delegatecall` (bytes memory)
            // but it will consume a little more gas
            assembly {
                returndatacopy(0x0, 0x0, returndatasize())
                return(0x0, returndatasize())
            }
        } else {
            revert();
        }
    }
}


/**
* @notice Base class for any staking contract (not usable with openzeppelin proxy)
* @dev Implement `isFallbackAllowed()` or override fallback function
* Implement `withdrawTokens(uint256)` and `withdrawETH()` functions
*/
abstract contract AbstractStakingContract is RawStakingContract {

    StakingInterfaceRouter immutable router_;
    NuCypherToken public immutable token;

    /**
    * @param _router Interface router contract address
    */
    constructor(StakingInterfaceRouter _router) {
        router_ = _router;
        NuCypherToken localToken = _router.target().token();
        require(address(localToken) != address(0));
        token = localToken;
    }

    /**
    * @dev Returns address of StakingInterfaceRouter
    */
    function router() public view override returns (StakingInterfaceRouter) {
        return router_;
    }

}


/**
* @notice Base class for any staking contract usable with openzeppelin proxy
* @dev Implement `isFallbackAllowed()` or override fallback function
* Implement `withdrawTokens(uint256)` and `withdrawETH()` functions
*/
abstract contract InitializableStakingContract is Initializable, RawStakingContract {

    StakingInterfaceRouter router_;
    NuCypherToken public token;

    /**
    * @param _router Interface router contract address
    */
    function initialize(StakingInterfaceRouter _router) public initializer {
        router_ = _router;
        NuCypherToken localToken = _router.target().token();
        require(address(localToken) != address(0));
        token = localToken;
    }

    /**
    * @dev Returns address of StakingInterfaceRouter
    */
    function router() public view override returns (StakingInterfaceRouter) {
        return router_;
    }

}
