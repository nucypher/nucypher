pragma solidity ^0.4.24;


import "zeppelin/ownership/Ownable.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";
import "zeppelin/math/SafeMath.sol";
import "contracts/NuCypherToken.sol";


/**
* @notice Contract that can call library contract
**/
contract Caller {
    /**
    * @notice Target contract address
    **/
    function target() public returns (address);
}


/**
* @notice Contract holds tokens for vesting.
* Also tokens can be used as a stake in the miners escrow contract
*
**/
contract UserEscrow is Ownable {
    using SafeERC20 for NuCypherToken;
    using SafeMath for uint256;

    event Deposited(address indexed sender, uint256 value, uint256 duration);
    event Withdrawn(address indexed owner, uint256 value);
    event RewardWithdrawn(address indexed owner, uint256 value);

    address public target;
    NuCypherToken public token;
    uint256 public lockedValue;
    uint256 public endLockTimestamp;

    /**
    * @param _target UserEscrowProxyInterface contract address
    * @param _token Token contract
    **/
    constructor(address _target, NuCypherToken _token) public {
        require(address(_token) != 0x0 && _target != 0x0);
        target = _target;
        token = _token;
    }

    /**
    * @notice Initial tokens deposit
    * @param _value Amount of token to deposit
    * @param _duration Duration of tokens locking
    **/
    function initialDeposit(uint256 _value, uint256 _duration) public {
        require(lockedValue == 0 && _value > 0);
        endLockTimestamp = block.timestamp.add(_duration);
        lockedValue = _value;
        token.safeTransferFrom(msg.sender, address(this), _value);
        emit Deposited(msg.sender, _value, _duration);
    }

    /**
    * @notice Get locked tokens value
    **/
    function getLockedTokens() public view returns (uint256) {
        if (endLockTimestamp <= block.timestamp) {
            return 0;
        }
        return lockedValue;
    }

    /**
    * @notice Withdraw available amount of tokens to owner
    * @param _value Amount of token to withdraw
    **/
    // TODO rename?
    function withdraw(uint256 _value) public onlyOwner {
        require(token.balanceOf(address(this)).sub(getLockedTokens()) >= _value);
        token.safeTransfer(owner, _value);
        emit Withdrawn(owner, _value);
    }

    /**
    * @notice Withdraw available reward to the owner
    **/
    function rewardWithdraw() public onlyOwner {
        uint256 balance = address(this).balance;
        require(balance != 0);
        owner.transfer(balance);
        emit RewardWithdrawn(owner, balance);
    }

    /**
    * @dev Fallback function send all requests to the target proxy contract
    **/
    function () public payable onlyOwner {
        assert(target != 0x0);
        address libraryTarget = Caller(target).target();
        assert(libraryTarget != 0x0);
        bool callSuccess = libraryTarget.delegatecall(msg.data);
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


/**
* @notice Contract links library with UserEscrow
**/
contract UserEscrowLibraryLinker is Ownable {

    address public target;

    /**
    * @param _target Address of the library contract
    **/
    constructor(address _target) {
        require(_target != 0x0);
        target = _target;
    }

    /**
    * @notice Upgrade library
    * @param _target New contract address
    **/
    function upgrade(address _target) public onlyOwner {
        require(_target != 0x0);
        target = _target;
    }

}