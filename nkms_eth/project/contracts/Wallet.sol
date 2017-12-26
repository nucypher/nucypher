pragma solidity ^0.4.8;


import "./zeppelin/token/BurnableToken.sol";
import "./zeppelin/token/SafeERC20.sol";
import "./zeppelin/math/SafeMath.sol";
import "./zeppelin/ownership/Ownable.sol";


/**
* @notice Contract holds and locks client tokens.
**/
contract Wallet is Ownable {
    using SafeERC20 for BurnableToken;
    using SafeMath for uint256;

    struct PeriodInfo {
        uint256 period;
        uint256 lockedValue;
    }

    address manager;
    BurnableToken token;
    uint256 public lockedValue;
    uint256 public lockedBlock;
    uint256 public releaseBlock;
    uint256 public decimals;
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
    **/
    function Wallet(BurnableToken _token) {
        token = _token;
        manager = msg.sender;
    }

    /**
    * @notice Sets locked tokens and time interval of locking
    * @param _value Amount of tokens which should lock
    * @param _releaseBlock Release block number
    * @param _lockedBlock Initial lock block number
    **/
    function setLock(uint256 _value, uint256 _releaseBlock, uint256 _lockedBlock)
        onlyManager
    {
        lockedValue = _value;
        releaseBlock = _releaseBlock;
        lockedBlock = _lockedBlock;
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
    function withdraw(uint256 _value) onlyOwner returns (bool success) {
        require(_value <= token.balanceOf(address(this)) - getLockedTokens());
        token.safeTransfer(msg.sender, _value);
        return true;
    }

    /**
    * @notice Get locked tokens value in a specified moment in time
    * @param _blockNumber Block number for checking
    **/
    function getLockedTokens(uint256 _blockNumber)
        public constant returns (uint256)
    {
        if (releaseBlock <= _blockNumber) {
            return 0;
        } else {
            return lockedValue;
        }
    }

    /**
    * @notice Get locked tokens value for current block
    **/
    function getLockedTokens() public constant returns (uint256) {
        return getLockedTokens(block.number);
    }

    /**
    * @notice Terminate contract and refund to owner
    * @dev The called token contracts could try to re-enter this contract.
    Only supply token contracts you trust.
    **/
    function destroy() onlyManager public returns (bool) {
        token.safeTransfer(owner, token.balanceOf(address(this)));
        selfdestruct(owner);
        return true;
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
    function deleteConfirmedPeriod(uint256 _number) onlyManager {
        var newNumberConfirmedPeriods = numberConfirmedPeriods - _number;
        for (uint256 i = 0; i < newNumberConfirmedPeriods; i++) {
            confirmedPeriods[i] = confirmedPeriods[_number + i];
        }
        numberConfirmedPeriods = newNumberConfirmedPeriods;
    }
}
