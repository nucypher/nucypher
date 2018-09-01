pragma solidity ^0.4.24;


import "zeppelin/ownership/Ownable.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";
import "zeppelin/math/SafeMath.sol";
import "contracts/NuCypherToken.sol";


/**
* @notice Contract links library with UserEscrow
**/
contract UserEscrowLibraryLinker is Ownable {

    address public target;
    bytes32 public secretHash;

    /**
    * @param _target Address of the library contract
    * @param _newSecretHash Secret hash (keccak256)
    **/
    constructor(address _target, bytes32 _newSecretHash) public {
        require(_target != 0x0);
        target = _target;
        secretHash = _newSecretHash;
    }

    /**
    * @notice Upgrade library
    * @param _target New contract address
    * @param _secret Secret for proof of contract owning
    * @param _newSecretHash New secret hash (keccak256)
    **/
    function upgrade(address _target, bytes _secret, bytes32 _newSecretHash) public onlyOwner {
        require(_target != 0x0);
        require(keccak256(_secret) == secretHash && _newSecretHash != secretHash);
        target = _target;
        secretHash = _newSecretHash;
    }

}


/**
* @notice Contract holds tokens for vesting.
* Also tokens can be used as a stake in the miners escrow contract
*
**/
contract UserEscrow is Ownable {
    using SafeERC20 for NuCypherToken;
    using SafeMath for uint256;

    event TokensDeposited(address indexed sender, uint256 value, uint256 duration);
    event TokensWithdrawn(address indexed owner, uint256 value);
    event ETHWithdrawn(address indexed owner, uint256 value);

    UserEscrowLibraryLinker public linker;
    NuCypherToken public token;
    uint256 public lockedValue;
    uint256 public endLockTimestamp;

    /**
    * @param _linker UserEscrowProxyInterface contract address
    * @param _token Token contract
    **/
    constructor(UserEscrowLibraryLinker _linker, NuCypherToken _token) public {
        require(address(_token) != 0x0 && address(_linker) != 0x0);
        linker = _linker;
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
        emit TokensDeposited(msg.sender, _value, _duration);
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
    function withdrawTokens(uint256 _value) public onlyOwner {
        require(token.balanceOf(address(this)).sub(getLockedTokens()) >= _value);
        token.safeTransfer(owner, _value);
        emit TokensWithdrawn(owner, _value);
    }

    /**
    * @notice Withdraw available ETH to the owner
    **/
    function withdrawETH() public onlyOwner {
        uint256 balance = address(this).balance;
        require(balance != 0);
        owner.transfer(balance);
        emit ETHWithdrawn(owner, balance);
    }

    /**
    * @dev Fallback function send all requests to the target proxy contract
    **/
    function () public payable onlyOwner {
        address libraryTarget = linker.target();
        require(libraryTarget != 0x0);
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