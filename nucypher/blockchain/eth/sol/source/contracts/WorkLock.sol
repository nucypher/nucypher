pragma solidity ^0.5.3;


import "zeppelin/math/SafeMath.sol";
import "contracts/NuCypherToken.sol";
import "contracts/MinersEscrow.sol";


/**
* @notice The WorkLock distribution contract
**/
contract WorkLock {
    using SafeMath for uint256;

    // TODO events

    struct WorkInfo {
        uint256 depositedETH;
        uint256 workDone;
        bool claimed;
    }

    NuCypherToken public token;
    MinersEscrow public escrow;
    uint256 public startBidDate;
    uint256 public endBidDate;
    // ETH -> NU
    uint256 public depositRate;
    // Work (reward in NU) -> ETH
    uint256 public refundRate;
    uint256 public minAllowableLockedTokens;
    uint256 public maxAllowableLockedTokens;
    uint256 public allClaimedTokens;
    uint16 public lockedPeriods;
    // TODO add some getters
    mapping(address => WorkInfo) public workInfo;

    // TODO docs
    constructor(
        NuCypherToken _token,
        MinersEscrow _escrow,
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
        allClaimedTokens = allClaimedTokens.add(newClaimedTokens);
        require(allClaimedTokens <= token.balanceOf(address(this)),
            "Not enough tokens in the contract");
    }

    /**
    * @notice Claimed tokens will be deposited and locked as stake in the MinersEscrow contract.
    **/
    function claim() public returns (uint256 claimedTokens) {
        require(block.timestamp >= endBidDate, "Claiming tokens allowed after bidding is over");
        WorkInfo storage info = workInfo[msg.sender];
        require(!info.claimed, "Tokens are already claimed");
        info.claimed = true;
        claimedTokens = info.depositedETH.mul(depositRate);
        info.workDone = escrow.setWorkMeasurement(msg.sender, true);
        token.approve(address(escrow), claimedTokens);
        escrow.deposit(msg.sender, claimedTokens, lockedPeriods);
    }

    /**
    * @notice Refund ETH for the work done
    **/
    function refund() public returns (uint256 refundETH) {
        WorkInfo storage info = workInfo[msg.sender];
        require(info.claimed, "Tokens are not claimed");
        require(info.depositedETH > 0, "Nothing deposited");
        uint256 currentWork = escrow.getWorkDone(msg.sender);
        uint256 workDone = currentWork.sub(info.workDone);
        require(workDone > 0, "No work has been done.");
        refundETH = workDone.div(refundRate);
        if (refundETH > info.depositedETH) {
            refundETH = info.depositedETH;
        }
        if (refundETH == info.depositedETH) {
            escrow.setWorkMeasurement(msg.sender, false);
        }
        info.depositedETH = info.depositedETH.sub(refundETH);
        info.workDone = info.workDone.add(refundETH.mul(refundRate));
        msg.sender.transfer(refundETH);
    }

}
