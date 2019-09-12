pragma solidity ^0.5.3;


import "zeppelin/math/SafeMath.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";
import "contracts/NuCypherToken.sol";
import "contracts/StakingEscrow.sol";


/**
* @notice The WorkLock distribution contract
**/
contract WorkLock {
    using SafeERC20 for NuCypherToken;
    using SafeMath for uint256;

    event Deposited(address indexed sender, uint256 value);
    event Bid(address indexed staker, uint256 depositedETH, uint256 claimedTokens);
    event Claimed(address indexed staker, uint256 claimedTokens);
    event Refund(address indexed staker, uint256 refundETH, uint256 completedWork);
    event Burn(address indexed sender, uint256 value);

    struct WorkInfo {
        uint256 depositedETH;
        uint256 completedWork;
        bool claimed;
    }

    NuCypherToken public token;
    StakingEscrow public escrow;
    uint256 public startBidDate;
    uint256 public endBidDate;
    // ETH -> NU
    uint256 public depositRate;
    // Work (reward in NU) -> ETH
    uint256 public refundRate;
    uint256 public minAllowableLockedTokens;
    uint256 public maxAllowableLockedTokens;
    uint256 public remainingTokens;
    uint16 public lockedPeriods;
    mapping(address => WorkInfo) public workInfo;

    /**
    * @param _token Token contract
    * @param _escrow Escrow contract
    * @param _startBidDate Timestamp when bidding starts
    * @param _endBidDate Timestamp when bidding will end
    * @param _depositRate ETH -> NU rate
    * @param _refundRate Work -> ETH rate
    * @param _lockedPeriods Number of periods during which claimed tokens will be locked
    **/
    constructor(
        NuCypherToken _token,
        StakingEscrow _escrow,
        uint256 _startBidDate,
        uint256 _endBidDate,
        uint256 _depositRate,
        uint256 _refundRate,
        uint16 _lockedPeriods
    )
        public
    {
        require(_token.totalSupply() > 0 &&
            _escrow.secondsPerPeriod() > 0 &&
            _endBidDate > _startBidDate &&
            _endBidDate > block.timestamp &&
            _depositRate > 0 &&
            _refundRate > 0 &&
            _lockedPeriods >= _escrow.minLockedPeriods());
        token = _token;
        escrow = _escrow;
        startBidDate = _startBidDate;
        endBidDate = _endBidDate;
        minAllowableLockedTokens = _escrow.minAllowableLockedTokens();
        maxAllowableLockedTokens = _escrow.maxAllowableLockedTokens();
        depositRate = _depositRate;
        refundRate = _refundRate;
        lockedPeriods = _lockedPeriods;
    }

    /**
    * @notice Deposit tokens to contract
    * @param _value Amount of tokens to transfer
    **/
    function deposit(uint256 _value) public {
        token.safeTransferFrom(msg.sender, address(this), _value);
        remainingTokens += _value;
        emit Deposited(msg.sender, _value);
    }

    /**
    * @notice Bid for tokens by transferring ETH
    **/
    function bid() public payable returns (uint256 newClaimedTokens) {
        require(block.timestamp >= startBidDate && block.timestamp <= endBidDate,
            "Bid is open during a certain period");
        WorkInfo storage info = workInfo[msg.sender];
        info.depositedETH = info.depositedETH.add(msg.value);
        uint256 claimedTokens = info.depositedETH.mul(depositRate);
        require(claimedTokens >= minAllowableLockedTokens && claimedTokens <= maxAllowableLockedTokens,
            "Claimed tokens must be within the allowed limits");
        newClaimedTokens = msg.value.mul(depositRate);
        remainingTokens = remainingTokens.sub(newClaimedTokens);
        emit Bid(msg.sender, msg.value, newClaimedTokens);
    }

    /**
    * @notice Claimed tokens will be deposited and locked as stake in the StakingEscrow contract.
    **/
    function claim() public returns (uint256 claimedTokens) {
        require(block.timestamp >= endBidDate, "Claiming tokens allowed after bidding is over");
        WorkInfo storage info = workInfo[msg.sender];
        require(!info.claimed, "Tokens are already claimed");
        info.claimed = true;
        claimedTokens = info.depositedETH.mul(depositRate);
        info.completedWork = escrow.setWorkMeasurement(msg.sender, true);
        token.approve(address(escrow), claimedTokens);
        escrow.deposit(msg.sender, claimedTokens, lockedPeriods);
        emit Claimed(msg.sender, claimedTokens);
    }

    /**
    * @notice Refund ETH for the completed work
    **/
    function refund() public returns (uint256 refundETH) {
        WorkInfo storage info = workInfo[msg.sender];
        require(info.claimed, "Tokens are not claimed");
        require(info.depositedETH > 0, "Nothing deposited");
        uint256 currentWork = escrow.getCompletedWork(msg.sender);
        uint256 completedWork = currentWork.sub(info.completedWork);
        require(completedWork > 0, "No work that has been completed.");
        refundETH = completedWork.div(refundRate);
        if (refundETH > info.depositedETH) {
            refundETH = info.depositedETH;
        }
        if (refundETH == info.depositedETH) {
            escrow.setWorkMeasurement(msg.sender, false);
        }
        info.depositedETH = info.depositedETH.sub(refundETH);
        completedWork = refundETH.mul(refundRate);
        info.completedWork = info.completedWork.add(completedWork);
        emit Refund(msg.sender, refundETH, completedWork);
        msg.sender.transfer(refundETH);
    }

    /**
    * @notice Get remaining work to full refund
    **/
    function getRemainingWork(address _staker) public view returns (uint256) {
        WorkInfo storage info = workInfo[_staker];
        uint256 completedWork = escrow.getCompletedWork(_staker).sub(info.completedWork);
        uint256 remainingWork = info.depositedETH.mul(refundRate);
        if (remainingWork <= completedWork) {
            return 0;
        }
        return remainingWork.sub(completedWork);
    }

    /**
    * @notice Burn unclaimed tokens
    **/
    function burnRemaining() public {
        require(block.timestamp >= endBidDate, "Burning tokens allowed when bidding is over");
        require(remainingTokens > 0, "There are no tokens that can be burned");
        token.approve(address(escrow), remainingTokens);
        escrow.burn(remainingTokens);
        emit Burn(msg.sender, remainingTokens);
    }

}
