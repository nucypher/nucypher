pragma solidity ^0.5.3;


import "zeppelin/ownership/Ownable.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";
import "zeppelin/math/SafeMath.sol";
import "zeppelin/utils/Address.sol";
import "contracts/NuCypherToken.sol";
import "contracts/staking_contracts/AbstractStakingContract.sol";

/**
* @notice StakingEscrow interface
**/
contract StakingEscrowInterface {
    function getLockedTokens(address _staker, uint16 _periods) public view returns (uint256);
    function secondsPerPeriod() public view returns (uint32);
}

/**
* @notice Contract holds tokens for vesting.
* Also tokens can be used as a stake in the staking escrow contract
**/
contract PreallocationEscrow is AbstractStakingContract, Ownable {
    using SafeERC20 for NuCypherToken;
    using SafeMath for uint256;
    using Address for address payable;

    event TokensDeposited(address indexed sender, uint256 value, uint256 duration);
    event TokensWithdrawn(address indexed owner, uint256 value);
    event ETHWithdrawn(address indexed owner, uint256 value);

    NuCypherToken public token;
    uint256 public lockedValue;
    uint256 public endLockTimestamp;
    StakingEscrowInterface public stakingEscrow;

    /**
    * @param _router Interface router contract address
    * @param _token Token contract
    **/
    constructor(StakingInterfaceRouter _router, NuCypherToken _token, StakingEscrowInterface _stakingEscrow) public AbstractStakingContract(_router) {
        // check that the input addresses are contract
        require(_token.totalSupply() > 0);
        require(_stakingEscrow.secondsPerPeriod() > 0);

        token = _token;
        stakingEscrow = _stakingEscrow;
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
        uint256 balance = token.balanceOf(address(this));
        uint32 secondsPerPeriod = stakingEscrow.secondsPerPeriod();
        uint16 currentPeriod = uint16(block.timestamp / secondsPerPeriod);
        uint16 endLockPeriod = uint16(endLockTimestamp / secondsPerPeriod);
        if (currentPeriod <= endLockPeriod) {
            uint256 stakedTokens = stakingEscrow.getLockedTokens(address(this), endLockPeriod - currentPeriod);
            uint256 lockedTokens = getLockedTokens();
            if (lockedTokens > stakedTokens) {
                balance = balance.sub(lockedTokens - stakedTokens);
            }
        }
        require(balance >= _value);
        token.safeTransfer(msg.sender, _value);
        emit TokensWithdrawn(msg.sender, _value);
    }

    /**
    * @notice Withdraw available ETH to the owner
    **/
    function withdrawETH() public onlyOwner {
        uint256 balance = address(this).balance;
        require(balance != 0);
        msg.sender.sendValue(balance);
        emit ETHWithdrawn(msg.sender, balance);
    }

    /**
    * @notice Calling fallback function is allowed only for the owner
    **/
    function isFallbackAllowed() public returns (bool) {
        return msg.sender == owner();
    }

}
