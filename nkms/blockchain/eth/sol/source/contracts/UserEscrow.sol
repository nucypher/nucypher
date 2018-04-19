pragma solidity ^0.4.18;

import "zeppelin/token/ERC20/SafeERC20.sol";
import "zeppelin/ownership/Ownable.sol";
import "zeppelin/math/SafeMath.sol";
import "contracts/NuCypherKMSToken.sol";
import "contracts/MinersEscrow.sol";
import "contracts/PolicyManager.sol";



/**
* @notice Contract holds tokens for vesting.
* Also tokens can be send to the miners escrow
**/
contract UserEscrow is Ownable {
    using SafeERC20 for NuCypherKMSToken;
    using SafeMath for uint256;

    event Deposited(address indexed sender, uint256 value, uint256 duration);
    event Withdrawn(address indexed owner, uint256 value);
    event DepositedAsMiner(address indexed owner, uint256 value, uint256 periods);
    event WithdrawnAsMiner(address indexed owner, uint256 value);
    event Locked(address indexed owner, uint256 value, uint256 periods);
    event LockSwitched(address indexed owner);
    event ActivityConfirmed(address indexed owner);
    event Mined(address indexed owner);
    event RewardWithdrawnAsMiner(address indexed owner, uint256 value);
    event RewardWithdrawn(address indexed owner, uint256 value);

    NuCypherKMSToken public token;
    MinersEscrow public escrow;
    PolicyManager public policyManager;
    uint256 public lockedValue;
    uint256 public endLockTimestamp;
    uint256 public lockDuration;

    /**
    * @notice Constructor sets addresses of the contracts
    * @param _token Token contract
    * @param _escrow Escrow contract
    * @param _policyManager PolicyManager contract
    **/
    function UserEscrow(
        NuCypherKMSToken _token,
        MinersEscrow _escrow,
        PolicyManager _policyManager
    )
        public
    {
        require(address(_token) != 0x0 &&
            address(_escrow) != 0x0 &&
            address(_policyManager) != 0x0);
        token = _token;
        escrow = _escrow;
        policyManager = _policyManager;
    }

    function () public payable {}

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
        Deposited(msg.sender, _value, _duration);
    }

    /**
    * @notice Get locked tokens value
    **/
    function getLockedTokens() public view returns (uint256) {
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
        Withdrawn(owner, _value);
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
        DepositedAsMiner(owner, _value, _periods);
    }

    /**
    * @notice Withdraw available amount of tokens from the miners escrow to the user escrow
    * @param _value Amount of token to withdraw
    **/
    function minerWithdraw(uint256 _value) public onlyOwner {
        escrow.withdraw(_value);
        WithdrawnAsMiner(owner, _value);
    }

    /**
    * @notice Lock some tokens or increase lock in the miners escrow
    * @param _value Amount of tokens which should lock
    * @param _periods Amount of periods during which tokens will be unlocked
    **/
    function lock(uint256 _value, uint256 _periods) public onlyOwner {
        escrow.lock(_value, _periods);
        Locked(owner, _value, _periods);
    }

    /**
    * @notice Switch lock in the miners escrow
    **/
    function switchLock() public onlyOwner {
        escrow.switchLock();
        LockSwitched(owner);
    }

    /**
    * @notice Confirm activity for future period in the miners escrow
    **/
    function confirmActivity() external onlyOwner {
        escrow.confirmActivity();
        ActivityConfirmed(owner);
    }

    /**
    * @notice Mint tokens in the miners escrow
    **/
    function mint() external onlyOwner {
        escrow.mint();
        Mined(owner);
    }

    /**
    * @notice Withdraw available reward from the policy manager to the user escrow
    **/
    function policyRewardWithdraw() public onlyOwner {
        uint256 balance = this.balance;
        policyManager.withdraw();
        RewardWithdrawnAsMiner(owner, this.balance - balance);
    }

    /**
    * @notice Withdraw available reward to the owner
    **/
    function rewardWithdraw() public onlyOwner {
        uint256 balance = this.balance;
        require(balance != 0);
        owner.transfer(balance);
        RewardWithdrawn(owner, balance);
    }

}
