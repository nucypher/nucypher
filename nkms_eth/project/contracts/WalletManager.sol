pragma solidity ^0.4.8;


import "./zeppelin/token/SafeERC20.sol";
import "./zeppelin/math/Math.sol";
import "./zeppelin/ownership/Ownable.sol";
import "./NuCypherKMSToken.sol";
import "./lib/LinkedList.sol";
import "./Miner.sol";
import "./Wallet.sol";


/**
* @notice Contract creates wallets and manage mining for that wallets
**/
contract WalletManager is Miner, Ownable {
    using LinkedList for LinkedList.Data;
    using SafeERC20 for NuCypherKMSToken;

    struct PeriodInfo {
        uint256 totalLockedValue;
        uint256 numberOwnersToBeRewarded;
    }

    uint256 constant MAX_PERIODS = 100;
    uint256 constant MAX_OWNERS = 50000;

    NuCypherKMSToken token;
    mapping (address => Wallet) public wallets;
    LinkedList.Data walletOwners;

    uint256 public blocksPerPeriod;
    mapping (uint256 => PeriodInfo) public lockedPerPeriod;
    uint256 public minReleasePeriods;

    /**
    * @notice The WalletManager constructor sets address of token contract and coefficients for mining
    * @param _token Token contract
    * @param _miningCoefficient Mining coefficient
    * @param _blocksPerPeriod Size of one period in blocks
    * @param _minReleasePeriods Min amount of periods during which tokens will be released
    * @param _lockedBlocksCoefficient Locked blocks coefficient
    * @param _awardedPeriods Max periods that will be additionally awarded
    **/
    function WalletManager(
        NuCypherKMSToken _token,
        uint256 _miningCoefficient,
        uint256 _blocksPerPeriod,
        uint256 _minReleasePeriods,
        uint256 _lockedBlocksCoefficient,
        uint256 _awardedPeriods
    )
        Miner(_token, _miningCoefficient, _lockedBlocksCoefficient, _awardedPeriods * _blocksPerPeriod)
    {
        require(_blocksPerPeriod != 0 && _minReleasePeriods != 0);
        token = _token;
        blocksPerPeriod = _blocksPerPeriod;
        minReleasePeriods = _minReleasePeriods;
    }

    /**
    * @dev Throws if called by account that have not wallet.
    */
    modifier walletExists() {
        require(walletOwners.valueExists(msg.sender));
        _;
    }

    /**
    * @notice Create wallet for user
    * @return Address of created wallet
    **/
    function createWallet() public returns (address) {
        require(!walletOwners.valueExists(msg.sender) &&
            walletOwners.sizeOf() < MAX_OWNERS);
        Wallet wallet = new Wallet(token, blocksPerPeriod, minReleasePeriods);
        wallet.transferOwnership(msg.sender);
        wallets[msg.sender] = wallet;
        walletOwners.push(msg.sender, true);
        return wallet;
    }

    /**
    * @notice Get locked tokens value for all owners in current period
    **/
    function getAllLockedTokens()
        public constant returns (uint256)
    {
        var period = block.number.div(blocksPerPeriod);
        return lockedPerPeriod[period].totalLockedValue;
    }

    /**
    * @notice Lock some tokens
    * @param _value Amount of tokens which should lock
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function lock(uint256 _value, uint256 _periods) walletExists external {
        // TODO add checking min _value
        Wallet wallet = wallets[msg.sender];
        wallet.lock(_value, _periods);
        confirmActivity(wallet.lockedValue());
    }

    /**
    * @notice Terminate contract and refund to owners
    * @dev The called token contracts could try to re-enter this contract.
    Only supply token contracts you trust.
    **/
    function destroy() onlyOwner external {
        // Transfer tokens to owners
        var current = walletOwners.step(0x0, true);
        while (current != 0x0) {
            wallets[current].destroy();
            current = walletOwners.step(current, true);
        }
        token.safeTransfer(owner, token.balanceOf(address(this)));

        // Transfer Eth to owner and terminate contract
        selfdestruct(owner);
    }

    /**
    * @notice Confirm activity for future period
    * @param _lockedValue Locked tokens in future period
    **/
    function confirmActivity(uint256 _lockedValue) internal {
        require(_lockedValue > 0);
        var wallet = wallets[msg.sender];
        var nextPeriod = block.number.div(blocksPerPeriod) + 1;

        var numberConfirmedPeriods = wallet.numberConfirmedPeriods();
        if (numberConfirmedPeriods > 0 &&
            wallet.getConfirmedPeriod(numberConfirmedPeriods - 1) == nextPeriod) {
            var confirmedPeriodValue = wallet.getConfirmedPeriodValue(numberConfirmedPeriods - 1);
            lockedPerPeriod[nextPeriod].totalLockedValue = lockedPerPeriod[nextPeriod].totalLockedValue
                .add(_lockedValue.sub(confirmedPeriodValue));
            wallet.setConfirmedPeriodValue(numberConfirmedPeriods - 1, _lockedValue);
            return;
        }

        require(numberConfirmedPeriods < MAX_PERIODS);
        lockedPerPeriod[nextPeriod].totalLockedValue += _lockedValue;
        lockedPerPeriod[nextPeriod].numberOwnersToBeRewarded++;
        wallet.addConfirmedPeriod(nextPeriod, _lockedValue);
    }

    /**
    * @notice Confirm activity for future period
    **/
    function confirmActivity() walletExists external {
        var wallet = wallets[msg.sender];
        var nextPeriod = block.number.div(blocksPerPeriod) + 1;

        var numberConfirmedPeriods = wallet.numberConfirmedPeriods();
        if (numberConfirmedPeriods > 0 &&
            wallet.getConfirmedPeriod(numberConfirmedPeriods - 1) >= nextPeriod) {
            return;
        }

        var currentPeriod = nextPeriod - 1;
        var lockedTokens = wallet.calculateLockedTokens(
            false, wallet.getLockedTokens(), 1);
        confirmActivity(lockedTokens);
    }

    /**
    * @notice Mint tokens for sender for previous periods if he locked his tokens and confirmed activity
    **/
    function mint() walletExists external {
        var previousPeriod = block.number.div(blocksPerPeriod).sub(1);
        var wallet = wallets[msg.sender];
        var numberPeriodsForMinting = wallet.numberConfirmedPeriods();
        require(numberPeriodsForMinting > 0 &&
            wallet.getConfirmedPeriod(0) <= previousPeriod);
        var currentLockedValue = wallet.getLockedTokens();
        var allLockedBlocks = wallet.calculateLockedPeriods(
            wallet.getConfirmedPeriodValue(numberPeriodsForMinting - 1))
            .add(numberPeriodsForMinting)
            .mul(blocksPerPeriod);
        var decimals = wallet.decimals();

        if (wallet.getConfirmedPeriod(numberPeriodsForMinting - 1) > previousPeriod) {
            numberPeriodsForMinting--;
        }
        if (wallet.getConfirmedPeriod(numberPeriodsForMinting - 1) > previousPeriod) {
            numberPeriodsForMinting--;
        }

        for(uint i = 0; i < numberPeriodsForMinting; ++i) {
            var (period, lockedValue) = wallet.confirmedPeriods(i);
            allLockedBlocks = allLockedBlocks.sub(blocksPerPeriod);
            (, decimals) = mint(
                wallet,
                lockedValue,
                lockedPerPeriod[period].totalLockedValue,
                blocksPerPeriod,
                allLockedBlocks,
                decimals);
            if (lockedPerPeriod[period].numberOwnersToBeRewarded > 1) {
                lockedPerPeriod[period].numberOwnersToBeRewarded--;
            } else {
                delete lockedPerPeriod[period];
            }
        }
        wallet.setDecimals(decimals);
        wallet.deleteConfirmedPeriods(numberPeriodsForMinting);

        // Update lockedValue for current period
        wallet.updateLockedTokens(currentLockedValue);
    }

    /**
    * @notice Fixed-step in cumulative sum
    * @param _start Starting point
    * @param _delta How much to step
    * @param _periods Amount of periods to get locked tokens
    * @dev
             _start
                v
      |-------->*--------------->*---->*------------->|
                |                      ^
                |                      stop
                |
                |       _delta
                |---------------------------->|
                |
                |                       shift
                |                      |----->|
    **/
    function findCumSum(address _start, uint256 _delta, uint256 _periods)
        public constant returns (address stop, uint256 shift)
    {
        require(walletOwners.valueExists(_start) && _periods > 0);
        var currentPeriod = block.number.div(blocksPerPeriod);
        uint256 distance = 0;
        var current = _start;

        if (current == 0x0) {
            current = walletOwners.step(current, true);
        }

        while (current != 0x0) {
            var wallet = wallets[current];
            var numberConfirmedPeriods = wallet.numberConfirmedPeriods();
            var period = currentPeriod;
            if (numberConfirmedPeriods > 0 &&
                wallet.getConfirmedPeriod(numberConfirmedPeriods - 1) == currentPeriod) {
                var lockedTokens = wallet.calculateLockedTokens(
                    true,
                    wallet.getConfirmedPeriodValue(numberConfirmedPeriods - 1),
                    _periods);
            } else if (numberConfirmedPeriods > 1 &&
                wallet.getConfirmedPeriod(numberConfirmedPeriods - 2) == currentPeriod) {
                lockedTokens = wallet.calculateLockedTokens(
                    true,
                    wallet.getConfirmedPeriodValue(numberConfirmedPeriods - 1),
                    _periods - 1);
            } else {
                current = walletOwners.step(current, true);
                continue;
            }

            if (_delta < distance + lockedTokens) {
                stop = current;
                shift = _delta - distance;
                break;
            } else {
                distance += lockedTokens;
                current = walletOwners.step(current, true);
            }
        }
    }
}
