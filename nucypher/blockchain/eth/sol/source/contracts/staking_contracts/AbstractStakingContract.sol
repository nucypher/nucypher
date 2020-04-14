pragma solidity ^0.6.5;


import "zeppelin/ownership/Ownable.sol";
import "zeppelin/utils/Address.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";
import "contracts/staking_contracts/StakingInterface.sol";


/**
* @notice Router for accessing interface contract
*/
contract StakingInterfaceRouter is Ownable {
    BaseStakingInterface public target;

    /**
    * @param _target Address of the interface contract
    */
    constructor(BaseStakingInterface _target) public {
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
* @notice Base class for any staking contract
* @dev Implement `isFallbackAllowed()` or override fallback function
* Implement `withdrawTokens(uint256)` and `withdrawETH()` functions
*/
abstract contract AbstractStakingContract {
    using Address for address;
    using Address for address payable;
    using SafeERC20 for NuCypherToken;

    StakingInterfaceRouter public immutable router;
    NuCypherToken public immutable token;

    /**
    * @param _router Interface router contract address
    */
    constructor(StakingInterfaceRouter _router) public {
        router = _router;
        NuCypherToken localToken = _router.target().token();
        require(address(localToken) != address(0));
        token = localToken;
    }

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

    /**
    * @dev Function sends all requests to the target contract
    */
    // TODO #1809
    fallback() external payable {
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
                returndatacopy(0x0, 0x0, returndatasize())
                return(0x0, returndatasize())
            }
        } else {
            revert();
        }
    }

}
