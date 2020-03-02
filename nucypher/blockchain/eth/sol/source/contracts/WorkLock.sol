pragma solidity ^0.5.3;


import "zeppelin/math/SafeMath.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";
import "zeppelin/utils/Address.sol";
import "contracts/NuCypherToken.sol";
import "contracts/StakingEscrow.sol";
import "contracts/lib/AdditionalMath.sol";


/**
* @notice The WorkLock distribution contract
*/
contract WorkLock {
    using SafeERC20 for NuCypherToken;
    using SafeMath for uint256;
    using AdditionalMath for uint256;
    using Address for address payable;
    using Address for address;

    event Deposited(address indexed sender, uint256 value);
    event Bid(address indexed sender, uint256 depositedETH);
    event Claimed(address indexed sender, uint256 claimedTokens);
    event Refund(address indexed sender, uint256 refundETH, uint256 completedWork);
    event Canceled(address indexed sender, uint256 value);
    event BiddersChecked(address indexed sender, uint256 startIndex, uint256 endIndex);
    event ClaimingEnabled(address indexed sender);
    event ForceRefund(address indexed sender, address indexed bidder, uint256 refundETH);

    struct WorkInfo {
        uint256 depositedETH;
        uint256 completedWork;
        bool claimed;
        uint256 index;
    }

    NuCypherToken public token;
    StakingEscrow public escrow;

    uint256 public startBidDate;
    uint256 public endBidDate;
    uint256 public endCancellationDate;

    /*
    * @dev WorkLock calculations:
    * depositRate = tokenSupply / ethSupply
    * claimedTokens = depositedETH * depositRate
    * refundRate = depositRate * SLOWING_REFUND / boostingRefund
    * refundETH = completedWork / refundRate
    */
    uint256 public boostingRefund;
    uint16 public constant SLOWING_REFUND = 100;
    uint256 private constant MAX_ETH_SUPPLY = 2e10 ether;

    uint256 public minAllowedBid;
    uint256 public maxAllowedBid;
    uint256 public tokenSupply;
    uint256 public ethSupply;
    uint16 public stakingPeriods;
    mapping(address => WorkInfo) public workInfo;

    address[] public bidders;
    // if value == bidders.length then WorkLock is fully checked
    uint256 public nextBidderToCheck;
    // copy from the escrow contract
    uint256 public defaultMaxAllowableLockedTokens;
    bool public isClaimingAvailable;

    /**
    * @dev Checks timestamp regarding cancellation window
    */
    modifier afterCancellationWindow()
    {
        require(block.timestamp >= endCancellationDate,
            "Operation is allowed when bidding and cancellation phases are over");
        _;
    }

    /**
    * @param _token Token contract
    * @param _escrow Escrow contract
    * @param _startBidDate Timestamp when bidding starts
    * @param _endBidDate Timestamp when bidding will end
    * @param _endCancellationDate Timestamp when cancellation will ends
    * @param _boostingRefund Coefficient to boost refund ETH
    * @param _stakingPeriods Amount of periods during which tokens will be locked after claiming
    * @param _minAllowedBid Minimum allowed ETH amount for bidding
    * @param _maxAllowedBid Maximum allowed ETH amount for bidding
    */
    constructor(
        NuCypherToken _token,
        StakingEscrow _escrow,
        uint256 _startBidDate,
        uint256 _endBidDate,
        uint256 _endCancellationDate,
        uint256 _boostingRefund,
        uint16 _stakingPeriods,
        uint256 _minAllowedBid,
        uint256 _maxAllowedBid
    )
        public
    {
        uint256 totalSupply = _token.totalSupply();
        require(totalSupply > 0 &&                              // token contract is deployed and accessible
            _escrow.secondsPerPeriod() > 0 &&                   // escrow contract is deployed and accessible
            _endBidDate > _startBidDate &&                      // bidding period lasts some time
            _endBidDate > block.timestamp &&                    // there is time to make a bid
            _endCancellationDate >= _endBidDate &&              // cancellation window includes bidding
            _boostingRefund > 0 &&                              // boosting coefficient was set
            _stakingPeriods >= _escrow.minLockedPeriods() &&    // staking duration is consistent with escrow contract
            _minAllowedBid <= _maxAllowedBid                    // maximum bid can't be lower than minimum
        );
        // worst case for `ethToWork()` and `workToETH()`,
        // when ethSupply == MAX_ETH_SUPPLY and tokenSupply == totalSupply
        require(MAX_ETH_SUPPLY * totalSupply * SLOWING_REFUND / MAX_ETH_SUPPLY / totalSupply == SLOWING_REFUND &&
            MAX_ETH_SUPPLY * totalSupply * _boostingRefund / MAX_ETH_SUPPLY / totalSupply == _boostingRefund);

        token = _token;
        escrow = _escrow;
        startBidDate = _startBidDate;
        endBidDate = _endBidDate;
        endCancellationDate = _endCancellationDate;
        boostingRefund = _boostingRefund;
        stakingPeriods = _stakingPeriods;
        minAllowedBid = _minAllowedBid;
        maxAllowedBid = _maxAllowedBid;
        defaultMaxAllowableLockedTokens = escrow.maxAllowableLockedTokens();
        isClaimingAvailable = false;
    }

    /**
    * @notice Deposit tokens to contract
    * @param _value Amount of tokens to transfer
    */
    function tokenDeposit(uint256 _value) external {
        require(block.timestamp < endBidDate, "Can't deposit more tokens after end of bidding");
        token.safeTransferFrom(msg.sender, address(this), _value);
        tokenSupply += _value;
        emit Deposited(msg.sender, _value);
    }

    /**
    * @notice Calculate amount of tokens that will be get for specified amount of ETH
    * @dev This value will be fixed only after end of bidding
    */
    function ethToTokens(uint256 _ethAmount) public view returns (uint256) {
        return _ethAmount.mul(tokenSupply).div(ethSupply);
    }

    /**
    * @notice Calculate amount of work that need to be done to refund specified amount of ETH
    * @dev This value will be fixed only after end of bidding
    */
    function ethToWork(uint256 _ethAmount) public view returns (uint256) {
        return _ethAmount.mul(tokenSupply).mul(SLOWING_REFUND).divCeil(ethSupply.mul(boostingRefund));
    }

    /**
    * @notice Calculate amount of ETH that will be refund for completing specified amount of work
    * @dev This value will be fixed only after end of bidding
    */
    function workToETH(uint256 _completedWork) public view returns (uint256) {
        return _completedWork.mul(ethSupply).mul(boostingRefund).div(tokenSupply.mul(SLOWING_REFUND));
    }

    /**
    * @notice Get remaining work to full refund
    */
    function getRemainingWork(address _bidder) external view returns (uint256) {
        WorkInfo storage info = workInfo[_bidder];
        uint256 completedWork = escrow.getCompletedWork(_bidder).sub(info.completedWork);
        uint256 remainingWork = ethToWork(info.depositedETH);
        if (remainingWork <= completedWork) {
            return 0;
        }
        return remainingWork - completedWork;
    }

    /**
    * @notice Get length of bidders array
    */
    function getBiddersLength() external view returns (uint256) {
        return bidders.length;
    }

    /**
    * @notice Bid for tokens by transferring ETH
    */
    function bid() external payable {
        require(block.timestamp >= startBidDate, "Bidding is not open yet");
        require(block.timestamp < endBidDate, "Bidding is already finished");
        WorkInfo storage info = workInfo[msg.sender];

        // first bid
        if (info.depositedETH == 0) {
            info.index = bidders.length;
            bidders.push(msg.sender);
        }

        info.depositedETH = info.depositedETH.add(msg.value);
        require(info.depositedETH >= minAllowedBid, "Bid must be more than minimum");
        require(info.depositedETH <= maxAllowedBid, "Bid must be less than maximum");
        ethSupply = ethSupply.add(msg.value);
        emit Bid(msg.sender, msg.value);
    }

    /**
    * @notice Cancel bid and refund deposited ETH
    */
    function cancelBid() external {
        require(block.timestamp < endCancellationDate, "Cancellation allowed only during bidding");
        WorkInfo storage info = workInfo[msg.sender];
        require(info.depositedETH > 0, "No bid to cancel");
        require(!info.claimed, "Tokens are already claimed");
        uint256 refundETH = info.depositedETH;
        info.depositedETH = 0;

        // remove from bidders array, move last bidder to the empty place
        uint256 length = bidders.length;
        if (info.index != length - 1) {
            address lastBidder = bidders[length - 1];
            bidders[info.index] = lastBidder;
            workInfo[lastBidder].index = info.index;
        }
        bidders.pop();

        ethSupply = ethSupply.sub(refundETH);
        msg.sender.sendValue(refundETH);
        emit Canceled(msg.sender, refundETH);
    }

    /**
    * @notice Make force refund to bidders who can get tokens more than maximum allowed
    * @param _biddersForRefund Sorted list of unique bidders. Only bidders who must receive a refund
    */
    function forceRefund(address payable[] calldata _biddersForRefund) external afterCancellationWindow {
        require(nextBidderToCheck != bidders.length, "Bidders have already been checked");

        uint256 length = _biddersForRefund.length;
        require(length > 0, "Must be at least one bidder for a refund");

        // TODO quit if can't be adjusted

        address previousBidder = _biddersForRefund[0];
        uint256 minBid = workInfo[previousBidder].depositedETH;
        uint256 maxBid = minBid;

        // get minimum and maximum bids
        for (uint256 i = 1; i < length; i++) {
            address bidder = _biddersForRefund[i];
            uint256 depositedETH = workInfo[bidder].depositedETH;
            require(bidder > previousBidder && depositedETH > 0, "Addresses must be an array of unique bidders");
            if (minBid > depositedETH) {
                minBid = depositedETH;
            } else if (maxBid < depositedETH) {
                maxBid = depositedETH;
            }
            previousBidder = bidder;
        }

        uint256[] memory refunds = new uint256[](length);
        // first step - align at a minimum bid
        if (minBid != maxBid) {
            for (uint256 i = 0; i < length; i++) {
                address bidder = _biddersForRefund[i];
                WorkInfo storage info = workInfo[bidder];
                if (info.depositedETH > minBid) {
                    refunds[i] = info.depositedETH - minBid;
                    info.depositedETH = minBid;
                    ethSupply -= refunds[i];
                }
            }
        }

        require(ethToTokens(minBid) > defaultMaxAllowableLockedTokens,
            "At least one of bidders has allowable bid");

        // final bids adjustment
        // (min_whale_bid * token_supply - max_stake * eth_supply) / (token_supply - max_stake * n_whales)
        uint256 refundETH = minBid.mul(tokenSupply)
                                .sub(defaultMaxAllowableLockedTokens.mul(ethSupply))
                                .divCeil(tokenSupply - defaultMaxAllowableLockedTokens.mul(length));
        uint256 resultBid = minBid.sub(refundETH);
        ethSupply -= length * refundETH;
        for (uint256 i = 0; i < length; i++) {
            address bidder = _biddersForRefund[i];
            WorkInfo storage info = workInfo[bidder];
            refunds[i] += refundETH;
            info.depositedETH = resultBid;
        }

        // reset verification
        nextBidderToCheck = 0;

        // transfer a refund
        for (uint256 i = 0; i < length; i++) {
            address payable bidder = _biddersForRefund[i];
            bidder.sendValue(refunds[i]);
            emit ForceRefund(msg.sender, bidder, refunds[i]);
        }

    }

    /**
    * @notice Check that the claimed tokens are within `maxAllowableLockedTokens` for all participants,
    * starting from the last point `nextBidderToCheck`
    * @dev Method stops working when the remaining gas is less than `_gasToSaveState`
    * and saves the state in `nextBidderToCheck`.
    * If all bidders have been checked then `nextBidderToCheck` will be equal to the length of the bidders array
    */
    function verifyBiddingCorrectness(uint256 _gasToSaveState) external afterCancellationWindow returns (uint256) {
        require(nextBidderToCheck != bidders.length, "Bidders have already been checked");

        uint256 maxBidFromMaxStake = defaultMaxAllowableLockedTokens.mul(ethSupply).div(tokenSupply);
        uint256 index = nextBidderToCheck;

        // skip checking if max boundary will be lower than default
        if (maxAllowedBid <= maxBidFromMaxStake) {
            index = bidders.length;
        }

        while (index < bidders.length && gasleft() > _gasToSaveState) {
            address bidder = bidders[index];
            require(workInfo[bidder].depositedETH <= maxBidFromMaxStake);
            index++;
        }

        if (index != nextBidderToCheck) {
            emit BiddersChecked(msg.sender, nextBidderToCheck, index);
            nextBidderToCheck = index;
        }
        return nextBidderToCheck;
    }

    /**
    * @notice Enable claiming after bidders have been checked.
    * @dev Finalize bounds of allowed locked tokens
    */
    function enableClaiming() external afterCancellationWindow {
        require(nextBidderToCheck == bidders.length, "Bidders have not been checked");
        require(!isClaimingAvailable,"Claiming is already enabled");

        uint256 min = ethToTokens(minAllowedBid);
        uint256 max = ethToTokens(maxAllowedBid);
        escrow.updateAllowableLockedTokens(min, max);
        emit ClaimingEnabled(msg.sender);

        isClaimingAvailable = true;
    }

    /**
    * @notice Claimed tokens will be deposited and locked as stake in the StakingEscrow contract.
    */
    function claim() external afterCancellationWindow returns (uint256 claimedTokens) {
        require(isClaimingAvailable, "Claiming has not been enabled yet");
        WorkInfo storage info = workInfo[msg.sender];
        require(!info.claimed, "Tokens are already claimed");
        claimedTokens = ethToTokens(info.depositedETH);
        require(claimedTokens > 0, "Nothing to claim");

        info.claimed = true;
        token.approve(address(escrow), claimedTokens);
        escrow.deposit(msg.sender, claimedTokens, stakingPeriods);
        info.completedWork = escrow.setWorkMeasurement(msg.sender, true);
        emit Claimed(msg.sender, claimedTokens);
    }

    /**
    * @notice Get available refund for bidder
    */
    function getAvailableRefund(address _bidder) public view returns (uint256) {
        WorkInfo storage info = workInfo[_bidder];
        // nothing to refund
        if (info.depositedETH == 0) {
            return 0;
        }

        uint256 currentWork = escrow.getCompletedWork(_bidder);
        uint256 completedWork = currentWork.sub(info.completedWork);
        // no work that has been completed since last refund
        if (completedWork == 0) {
            return 0;
        }

        uint256 refundETH = workToETH(completedWork);
        if (refundETH > info.depositedETH) {
            refundETH = info.depositedETH;
        }
        return refundETH;
    }

    /**
    * @notice Refund ETH for the completed work
    */
    function refund() external returns (uint256 refundETH) {
        refundETH = getAvailableRefund(msg.sender);
        require(refundETH > 0, "Nothing to refund: there is no ETH to refund or no completed work");

        WorkInfo storage info = workInfo[msg.sender];
        if (refundETH == info.depositedETH) {
            escrow.setWorkMeasurement(msg.sender, false);
        }
        info.depositedETH = info.depositedETH.sub(refundETH);
        // convert refund back to work to eliminate potential rounding errors
        uint256 completedWork = ethToWork(refundETH);

        info.completedWork = info.completedWork.add(completedWork);
        emit Refund(msg.sender, refundETH, completedWork);
        msg.sender.sendValue(refundETH);
    }
}
