pragma solidity ^0.4.0;


import "./zeppelin/token/SafeERC20.sol";
import "./zeppelin/ownership/Ownable.sol";
import "./zeppelin/math/SafeMath.sol";
import "./NuCypherKMSToken.sol";
import "./MinersEscrow.sol";


/**
* @notice Contract holds tokens for vesting.
Also tokens can be send to the miners escrow
**/
contract UserEscrow is Ownable {
    using SafeERC20 for NuCypherKMSToken;
    using SafeMath for uint256;

    NuCypherKMSToken public token;
    MinersEscrow public escrow;
    uint256 public lockedValue;
    uint256 public endLockTimestamp;
    uint256 public lockDuration;

    /**
    * @notice Constructor sets addresses of the token and the escrow contracts
    * @param _token Token contract
    * @param _escrow Escrow contract
    **/
    function UserEscrow(
        NuCypherKMSToken _token,
        MinersEscrow _escrow
    ){
        require(address(_token) != 0x0 &&
            address(_escrow) != 0x0);
        token = _token;
        escrow = _escrow;
    }

    /**
    * @notice Initial tokens deposit
    * @param _value Amount of token to deposit
    * @param _duration Duration of tokens locking
    **/
    function initialDeposit(uint256 _value, uint256 _duration) public {
        require(lockedValue == 0 && _value > 0);
        endLockTimestamp = block.timestamp.add(_duration);
        lockDuration = _duration;
        lockedValue = _value;
        token.safeTransferFrom(msg.sender, address(this), _value);
    }

    /**
    * @notice Get locked tokens value
    **/
    function getLockedTokens() public constant returns (uint256) {
        if (endLockTimestamp <= block.timestamp) {
            return 0;
        }
        return lockedValue.mul(endLockTimestamp.sub(block.timestamp))
            .div(lockDuration);
    }

    /**
    * @notice Withdraw available amount of tokens to owner
    * @param _value Amount of token to withdraw
    **/
    function withdraw(uint256 _value) public onlyOwner {
        require(token.balanceOf(address(this)).sub(getLockedTokens()) >= _value);
        token.safeTransfer(owner, _value);
    }

    /**
    * @notice Deposit tokens to the miners escrow
    * @param _value Amount of token to deposit
    * @param _periods Amount of periods during which tokens will be unlocked
    **/
    function minerDeposit(uint256 _value, uint256 _periods) public onlyOwner {
        require(token.balanceOf(address(this)) > _value);
        token.approve(address(escrow), _value);
        escrow.deposit(_value, _periods);
    }

    /**
    * @notice Withdraw available amount of tokens from the miners escrow to the user escrow
    * @param _value Amount of token to withdraw
    **/
    function minerWithdraw(uint256 _value) public onlyOwner {
        escrow.withdraw(_value);
    }

    /**
    * @notice Withdraw all amount of tokens back to user escrow (only if no locked)
    **/
    function minerWithdrawAll() public onlyOwner {
        escrow.withdrawAll();
    }

    /**
    * @notice Lock some tokens or increase lock in the miners escrow
    * @param _value Amount of tokens which should lock
    * @param _periods Amount of periods during which tokens will be unlocked
    **/
    function lock(uint256 _value, uint256 _periods) public onlyOwner {
        escrow.lock(_value, _periods);
    }

    /**
    * @notice Switch lock in the miners escrow
    **/
    function switchLock() public onlyOwner {
        escrow.switchLock();
    }

    /**
    * @notice Confirm activity for future period in the miners escrow
    **/
    function confirmActivity() external onlyOwner {
        escrow.confirmActivity();
    }

    /**
    * @notice Mint tokens  in the miners escrow
    **/
    function mint() external onlyOwner {
        escrow.mint();
    }

}
