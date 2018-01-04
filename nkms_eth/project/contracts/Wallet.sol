pragma solidity ^0.4.8;


import "./NuCypherKMSToken.sol";
import "./zeppelin/token/SafeERC20.sol";
import "./zeppelin/math/SafeMath.sol";
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
    uint256 public lockedValue;
    uint256 public decimals;
    uint256 public releasePeriod;
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
    **/
    function Wallet(NuCypherKMSToken _token, uint256 _blocksPerPeriod) {
        token = _token;
        manager = msg.sender;
        blocksPerPeriod = _blocksPerPeriod;
    }

    /**
    * @notice Calculate locked tokens value in next period
    * @param _period Current or future period
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
        var nextPeriod = _period + _periods;
        if (releasePeriod <= nextPeriod) {
            return 0;
        } else {
            return _lockedTokens;
        }
    }

    /**
    * @notice Calculate locked tokens value in next period
    **/
    function calculateLockedTokens() public constant returns (uint256) {
        var period = block.number.div(blocksPerPeriod);
        return calculateLockedTokens(period, getLockedTokens(), 1);
    }

    /**
    * @notice Lock some tokens
    * @param _value Amount of tokens which should lock
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function lock(uint256 _value, uint256 _periods) onlyManager {
        require(_value != 0 || _periods != 0);

        var lockedTokens = getLockedTokens();
        require(_value <= token.balanceOf(address(this)).sub(lockedTokens));

        if (lockedTokens == 0) {
            lockedValue = _value;
            releasePeriod = block.number.div(blocksPerPeriod).add(_periods).add(1);
        } else {
            lockedValue = lockedValue.add(_value);
            releasePeriod = releasePeriod.add(_periods);
        }
    }

    /**
    * @notice Get locked tokens value in current or future period
    * @param _block Current or future block number
    **/
    function getLockedTokens(uint256 _block)
        public constant returns (uint256)
    {
        require(_block >= block.number);

        var period = _block.div(blocksPerPeriod);

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
    * @notice Get locked tokens value
    **/
    function getLockedTokens() public constant returns (uint256) {
        return getLockedTokens(block.number);
    }

    /**
    * @notice Sets locked tokens
    * @param _value Amount of tokens which should lock
    **/
    function setLock(uint256 _value) onlyManager {
        lockedValue = _value;
    }

    /**
    * @notice Withdraw available amount of tokens back to owner
    * @param _value Amount of token to withdraw
    **/
    function withdraw(uint256 _value) onlyOwner {
        require(_value <= token.balanceOf(address(this)) - getLockedTokens());
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
    **/
    function addConfirmedPeriod(uint256 _period) onlyManager {
        if (numberConfirmedPeriods < confirmedPeriods.length) {
            confirmedPeriods[numberConfirmedPeriods].period = _period;
            confirmedPeriods[numberConfirmedPeriods].lockedValue = lockedValue;
        } else {
            confirmedPeriods.push(PeriodInfo(_period, lockedValue));
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
