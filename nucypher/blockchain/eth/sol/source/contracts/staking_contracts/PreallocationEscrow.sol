pragma solidity ^0.5.3;


import "zeppelin/ownership/Ownable.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";
import "zeppelin/math/SafeMath.sol";
import "contracts/NuCypherToken.sol";
import "contracts/staking_contracts/AbstractStakingContract.sol";


/**
* @notice Contract holds tokens for vesting.
* Also tokens can be used as a stake in the staking escrow contract
**/
contract PreallocationEscrow is AbstractStakingContract, Ownable {
    using SafeERC20 for NuCypherToken;
    using SafeMath for uint256;

    event TokensDeposited(address indexed sender, uint256 value, uint256 duration);
    event TokensWithdrawn(address indexed owner, uint256 value);
    event ETHWithdrawn(address indexed owner, uint256 value);

    NuCypherToken public token;
    uint256 public lockedValue;
    uint256 public endLockTimestamp;

    /**
    * @param _router Interface router contract address
    * @param _token Token contract
    **/
    constructor(StakingInterfaceRouter _router, NuCypherToken _token) public AbstractStakingContract(_router) {
        // check that the input address is contract
        require(_token.totalSupply() > 0);
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
        token.safeTransfer(msg.sender, _value);
        emit TokensWithdrawn(msg.sender, _value);
    }

    /**
    * @notice Withdraw available ETH to the owner
    **/
    function withdrawETH() public onlyOwner {
        uint256 balance = address(this).balance;
        require(balance != 0);
        msg.sender.transfer(balance);
        emit ETHWithdrawn(msg.sender, balance);
    }

    /**
    * @notice Calling fallback function is allowed only for the owner
    **/
    function isFallbackAllowed() public returns (bool) {
        return msg.sender == owner();
    }

}
