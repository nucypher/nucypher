// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.7.0;


import "zeppelin/ownership/Ownable.sol";
import "zeppelin/math/SafeMath.sol";
import "contracts/staking_contracts/AbstractStakingContract.sol";


/**
* @notice Contract holds tokens for vesting.
* Also tokens can be used as a stake in the staking escrow contract
*/
contract PreallocationEscrow is AbstractStakingContract, Ownable {
    using SafeMath for uint256;
    using SafeERC20 for NuCypherToken;
    using Address for address payable;

    event TokensDeposited(address indexed sender, uint256 value, uint256 duration);
    event TokensWithdrawn(address indexed owner, uint256 value);
    event ETHWithdrawn(address indexed owner, uint256 value);

    StakingEscrow public immutable stakingEscrow;

    uint256 public lockedValue;
    uint256 public endLockTimestamp;

    /**
    * @param _router Address of the StakingInterfaceRouter contract
    */
    constructor(StakingInterfaceRouter _router) AbstractStakingContract(_router) {
        stakingEscrow = _router.target().escrow();
    }

    /**
    * @notice Initial tokens deposit
    * @param _sender Token sender
    * @param _value Amount of token to deposit
    * @param _duration Duration of tokens locking
    */
    function initialDeposit(address _sender, uint256 _value, uint256 _duration) internal {
        require(lockedValue == 0 && _value > 0);
        endLockTimestamp = block.timestamp.add(_duration);
        lockedValue = _value;
        token.safeTransferFrom(_sender, address(this), _value);
        emit TokensDeposited(_sender, _value, _duration);
    }

    /**
    * @notice Initial tokens deposit
    * @param _value Amount of token to deposit
    * @param _duration Duration of tokens locking
    */
    function initialDeposit(uint256 _value, uint256 _duration) external {
        initialDeposit(msg.sender, _value, _duration);
    }

    /**
    * @notice Implementation of the receiveApproval(address,uint256,address,bytes) method
    * (see NuCypherToken contract). Initial tokens deposit
    * @param _from Sender
    * @param _value Amount of tokens to deposit
    * @param _tokenContract Token contract address
    * @notice (param _extraData) Amount of seconds during which tokens will be locked
    */
    function receiveApproval(
        address _from,
        uint256 _value,
        address _tokenContract,
        bytes calldata /* _extraData */
    )
        external
    {
        require(_tokenContract == address(token) && msg.sender == address(token));

        // Copy first 32 bytes from _extraData, according to calldata memory layout:
        //
        // 0x00: method signature      4 bytes
        // 0x04: _from                 32 bytes after encoding
        // 0x24: _value                32 bytes after encoding
        // 0x44: _tokenContract        32 bytes after encoding
        // 0x64: _extraData pointer    32 bytes. Value must be 0x80 (offset of _extraData wrt to 1st parameter)
        // 0x84: _extraData length     32 bytes
        // 0xA4: _extraData data       Length determined by previous variable
        //
        // See https://solidity.readthedocs.io/en/latest/abi-spec.html#examples

        uint256 payloadSize;
        uint256 payload;
        assembly {
            payloadSize := calldataload(0x84)
            payload := calldataload(0xA4)
        }
        payload = payload >> 8*(32 - payloadSize);
        initialDeposit(_from, _value, payload);
    }

    /**
    * @notice Get locked tokens value
    */
    function getLockedTokens() public view returns (uint256) {
        if (endLockTimestamp <= block.timestamp) {
            return 0;
        }
        return lockedValue;
    }

    /**
    * @notice Withdraw available amount of tokens to owner
    * @param _value Amount of token to withdraw
    */
    function withdrawTokens(uint256 _value) public override onlyOwner {
        uint256 balance = token.balanceOf(address(this));
        require(balance >= _value);
        // Withdrawal invariant for PreallocationEscrow:
        // After withdrawing, the sum of all escrowed tokens (either here or in StakingEscrow) must exceed the locked amount
        require(balance - _value + stakingEscrow.getAllTokens(address(this)) >= getLockedTokens());
        token.safeTransfer(msg.sender, _value);
        emit TokensWithdrawn(msg.sender, _value);
    }

    /**
    * @notice Withdraw available ETH to the owner
    */
    function withdrawETH() public override onlyOwner {
        uint256 balance = address(this).balance;
        require(balance != 0);
        msg.sender.sendValue(balance);
        emit ETHWithdrawn(msg.sender, balance);
    }

    /**
    * @notice Calling fallback function is allowed only for the owner
    */
    function isFallbackAllowed() public view override returns (bool) {
        return msg.sender == owner();
    }

}
