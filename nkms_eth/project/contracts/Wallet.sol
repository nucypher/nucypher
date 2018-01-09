pragma solidity ^0.4.8;


import "./NuCypherKMSToken.sol";
import "./zeppelin/token/SafeERC20.sol";
import "./zeppelin/math/SafeMath.sol";
import "./zeppelin/math/Math.sol";
import "./zeppelin/ownership/Ownable.sol";


/**
* @notice Contract holds and locks client tokens.
**/
contract Wallet is Ownable {
    using SafeERC20 for NuCypherKMSToken;
    using SafeMath for uint256;

    struct PeriodInfo {
        uint256 period;
        uint256 lockedValue;
    }

    address public manager;
    NuCypherKMSToken public token;
    uint256 public blocksPerPeriod;
    uint256 public minReleasePeriods;

    uint256 public lockedValue;
    uint256 public decimals;
    // last period before the tokens begin to unlock
    uint256 releasePeriod;
    uint256 releaseRate;
    PeriodInfo[] public confirmedPeriods;
    uint256 public numberConfirmedPeriods;

    /**
    * @dev Throws if called by any account other than the manager.
    **/
    modifier onlyManager() {
        require(msg.sender == manager);
        _;
    }

    /**
    * @notice Wallet constructor set token contract
    * @param _token Token contract
    * @param _blocksPerPeriod Size of one period in blocks
    * @param _minReleasePeriods Min amount of periods during which tokens will be released
    **/
    function Wallet(NuCypherKMSToken _token,
        uint256 _blocksPerPeriod,
        uint256 _minReleasePeriods
    ) {
        token = _token;
        manager = msg.sender;
        blocksPerPeriod = _blocksPerPeriod;
        minReleasePeriods = _minReleasePeriods;
    }

    /**
    * @notice Get locked tokens value in current period
    **/
    function getLockedTokens()
        public constant returns (uint256)
    {
        var period = block.number.div(blocksPerPeriod);

        // no confirmed periods, so current period may be release period
        if (numberConfirmedPeriods == 0) {
            var lockedValueToCheck = lockedValue;
        } else {
            var i = numberConfirmedPeriods - 1;
            var confirmedPeriod = confirmedPeriods[i].period;
            // last confirmed period is current period
            if (confirmedPeriod == period) {
                return confirmedPeriods[i].lockedValue;
            // last confirmed period is previous periods, so current period may be release period
            } else if (confirmedPeriod < period) {
                lockedValueToCheck = confirmedPeriods[i].lockedValue;
            // penultimate confirmed period is previous or current period, so get its lockedValue
            } else if (numberConfirmedPeriods > 1) {
                return confirmedPeriods[numberConfirmedPeriods - 2].lockedValue;
            // no previous periods, so return saved lockedValue
            } else {
                return lockedValue;
            }
        }
        // checks if owner can mine more tokens (before or after release period)
        if (calculateLockedTokens(period, lockedValueToCheck, 1) == 0) {
            return 0;
        } else {
            return lockedValueToCheck;
        }
    }

    /**
    * @notice Calculate locked tokens value in next period
    * @param _period Current or future period number
    * @param _lockedTokens Locked tokens in specified period
    * @param _periods Number of periods after _period that need to calculate
    * @return Calculated locked tokens in next period
    **/
    function calculateLockedTokens(
        uint256 _period,
        uint256 _lockedTokens,
        uint256 _periods
    )
        public constant returns (uint256)
    {
        var nextPeriod = _period.add(_periods);
        if (releasePeriod != 0 && releasePeriod < nextPeriod) {
            var period = Math.max256(_period, releasePeriod);
            var unlockedTokens = nextPeriod.sub(period).mul(releaseRate);
            return unlockedTokens <= _lockedTokens ? _lockedTokens.sub(unlockedTokens) : 0;
        } else {
            return _lockedTokens;
        }
    }

    /**
    * @notice Calculate locked tokens value in next period
    * @param _periods Number of periods after current that need to calculate
    * @return Calculated locked tokens in next period
    **/
    function calculateLockedTokens(uint256 _periods)
        public constant returns (uint256)
    {
        require(_periods > 0);
        var currentPeriod = block.number.div(blocksPerPeriod);
        var nextPeriod = currentPeriod.add(_periods);

        if (numberConfirmedPeriods > 0 &&
            confirmedPeriods[numberConfirmedPeriods - 1].period >= currentPeriod) {
            var lockedTokens = confirmedPeriods[numberConfirmedPeriods - 1].lockedValue;
            var period = confirmedPeriods[numberConfirmedPeriods - 1].period;
        } else {
            lockedTokens = getLockedTokens();
            period = currentPeriod;
        }
        var periods = nextPeriod.sub(period);

        return calculateLockedTokens(period, lockedTokens, periods);
    }

    /**
    * @notice Lock some tokens
    * @param _value Amount of tokens which should lock
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function lock(uint256 _value, uint256 _periods) onlyManager public {
        require(_value != 0 || _periods != 0);

        var lockedTokens = calculateLockedTokens(1);
        require(_value <= token.balanceOf(address(this)).sub(lockedTokens));

        var currentPeriod = block.number.div(blocksPerPeriod);
        if (lockedTokens == 0) {
            lockedValue = _value;
            releasePeriod = currentPeriod.add(_periods);
            releaseRate = _value.div(minReleasePeriods);
        } else {
            lockedValue = lockedTokens.add(_value);
            var period = Math.max256(releasePeriod, currentPeriod);
            releasePeriod = period.add(_periods);
        }
    }

    /**
    * @notice Sets locked tokens
    * @param _value Amount of tokens which should lock
    **/
    function updateLock(uint256 _value) onlyManager public {
        lockedValue = _value;
    }

    /**
    * @notice Withdraw available amount of tokens back to owner
    * @param _value Amount of token to withdraw
    **/
    function withdraw(uint256 _value) onlyOwner public {
        require(_value <= token.balanceOf(address(this)).sub(getLockedTokens()));
        token.safeTransfer(msg.sender, _value);
    }

    /**
    * @notice Terminate contract and refund to owner
    * @dev The called token contracts could try to re-enter this contract.
    Only supply token contracts you trust.
    **/
    function destroy() onlyManager public {
        token.safeTransfer(owner, token.balanceOf(address(this)));
        selfdestruct(owner);
    }

    /**
    * @notice Set minted decimals
    **/
    function setDecimals(uint256 _decimals) onlyManager {
        decimals = _decimals;
    }

    /**
    * @notice Get confirmed period
    * @param _index Index of period
    **/
    function getConfirmedPeriod(uint256 _index) public constant returns (uint256) {
        return confirmedPeriods[_index].period;
    }

    /**
    * @notice Get locked value for confirmed period
    * @param _index Index of period
    **/
    function getConfirmedPeriodValue(uint256 _index) public constant returns (uint256) {
        return confirmedPeriods[_index].lockedValue;
    }

    /**
    * @notice Set locked value for confirmed period
    * @param _index Index of period
    * @param _value Locked tokens
    **/
    function setConfirmedPeriodValue(uint256 _index, uint256 _value) onlyManager {
        confirmedPeriods[_index].lockedValue = _value;
    }

    /**
    * @notice Add period as confirmed
    * @param _period Period to add
    * @param _lockedValue Locked tokens for period
    **/
    function addConfirmedPeriod(uint256 _period, uint256 _lockedValue) onlyManager {
        if (numberConfirmedPeriods < confirmedPeriods.length) {
            confirmedPeriods[numberConfirmedPeriods].period = _period;
            confirmedPeriods[numberConfirmedPeriods].lockedValue = _lockedValue;
        } else {
            confirmedPeriods.push(PeriodInfo(_period, _lockedValue));
        }
        numberConfirmedPeriods++;
    }

    /**
    * @notice Clear periods array
    * @param _number Number of periods to delete
    **/
    function deleteConfirmedPeriods(uint256 _number) onlyManager {
        var newNumberConfirmedPeriods = numberConfirmedPeriods - _number;
        for (uint256 i = 0; i < newNumberConfirmedPeriods; i++) {
            confirmedPeriods[i] = confirmedPeriods[_number + i];
        }
        numberConfirmedPeriods = newNumberConfirmedPeriods;
    }
}
