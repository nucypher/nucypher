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
    }

    NuCypherToken public token;
    MinersEscrow public escrow;
    // ETH -> NU
    uint256 public depositRate;
    // Work (reward in NU) -> ETH
    uint256 public refundRate;
    uint16 public lockedPeriods;
    mapping(address => WorkInfo) workInfo;

    /**
    * @notice Claim tokens by transferring ETH. Claimed tokens will be deposited and locked as stake
    * in the MinersEscrow contract.
    **/
    function claim() public payable returns (uint256 claimedTokens) {
        claimedTokens = msg.value.mul(depositRate);
        require(token.balanceOf(address(this)) >= claimedTokens, "Not enough tokens in the contract");
        WorkInfo storage info = workInfo[msg.sender];
        if (info.depositedETH == 0) {
            info.workDone = escrow.setWorkMeasurement(msg.sender, true);
        }
        info.depositedETH = info.depositedETH.add(msg.value);
        token.approve(address(escrow), claimedTokens);
        escrow.deposit(msg.sender, claimedTokens, lockedPeriods);
    }

    /**
    * @notice Refund ETH for the work done
    **/
    function refund() public {
        WorkInfo storage info = workInfo[msg.sender];
        require(info.depositedETH > 0, "Nothing deposited");
        uint256 currentWork = escrow.getWorkDone(msg.sender);
        uint256 workDone = currentWork.sub(info.workDone);
        require(workDone > 0, "No work has been done.");
        uint256 refundETH = workDone.div(refundRate);
        if (refundETH > info.depositedETH) {
            refundETH = info.depositedETH;
            escrow.setWorkMeasurement(msg.sender, false);
        }
        info.depositedETH = info.depositedETH.sub(refundETH);
        info.workDone = currentWork;
        msg.sender.transfer(refundETH);
    }

}
