pragma solidity ^0.4.23;


import "zeppelin/token/ERC20/SafeERC20.sol";
import "./lib/AdditionalMath.sol";
import "contracts/Issuer.sol";


/**
* @notice PolicyManager interface
**/
contract PolicyManagerInterface {
    function updateReward(address _node, uint256 _period) external;
    function escrow() public view returns (address);
}


/**
* @notice Contract holds and locks miners tokens.
Each miner that lock its tokens will receive some compensation
**/
contract MinersEscrow is Issuer {
    using SafeERC20 for NuCypherToken;
    using AdditionalMath for uint256;

    event Deposited(address indexed owner, uint256 value, uint256 periods);
    event Locked(address indexed owner, uint256 value, uint256 firstPeriod, uint256 periods);
    event Divided(
        address indexed owner,
        uint256 oldValue,
        uint256 lastPeriod,
        uint256 newValue,
        uint256 periods
    );
    event Withdrawn(address indexed owner, uint256 value);
    event ActivityConfirmed(address indexed owner, uint256 indexed period, uint256 value);
    event Mined(address indexed owner, uint256 indexed period, uint256 value);

    struct StakeInfo {
        uint256 firstPeriod;
        uint256 lastPeriod;
        uint256 periods;
        uint256 lockedValue;
    }

    struct Downtime {
        uint256 startPeriod;
        uint256 endPeriod;
    }

    struct MinerInfo {
        uint256 value;
        uint256 decimals;
        /*
        * Periods that confirmed but not yet mined, two values instead of array for optimisation.
        * lock() and confirmActivity() methods include mint() method so may be only two confirmed
        * but not yet mined periods - current and next periods. There is no order between them because of
        * storage savings. So each time should check values of both variables.
        * EMPTY_CONFIRMED_PERIOD constant is used as removed value
        */
        uint256 confirmedPeriod1;
        uint256 confirmedPeriod2;
        // downtime
        uint256 lastActivePeriod;
        Downtime[] downtime;
        StakeInfo[] stakes;
        bytes32[] minerIds;
    }

    /*
    * Used as removed value for confirmedPeriod1(2).
    * Non zero value decreases gas usage in some executions of confirmActivity() method
    * but increases gas usage in mint() method. In both cases confirmActivity()
    * with one execution of mint() method consume the same amount of gas
    */
    uint256 constant EMPTY_CONFIRMED_PERIOD = 0;
    uint256 constant RESERVED_PERIOD = 0;
    uint256 constant MAX_CHECKED_VALUES = 5;

    mapping (address => MinerInfo) public minerInfo;
    address[] public miners;

    mapping (uint256 => uint256) public lockedPerPeriod;
    uint256 public minLockedPeriods;
    uint256 public minAllowableLockedTokens;
    uint256 public maxAllowableLockedTokens;
    PolicyManagerInterface public policyManager;

    /**
    * @notice Constructor sets address of token contract and coefficients for mining
    * @param _token Token contract
    * @param _hoursPerPeriod Size of period in hours
    * @param _miningCoefficient Mining coefficient
    * @param _minLockedPeriods Min amount of periods during which tokens will be locked
    * @param _lockedPeriodsCoefficient Locked blocks coefficient
    * @param _awardedPeriods Max periods that will be additionally awarded
    * @param _minAllowableLockedTokens Min amount of tokens that can be locked
    * @param _maxAllowableLockedTokens Max amount of tokens that can be locked
    **/
    constructor(
        NuCypherToken _token,
        uint256 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint256 _awardedPeriods,
        uint256 _minLockedPeriods,
        uint256 _minAllowableLockedTokens,
        uint256 _maxAllowableLockedTokens
    )
        public
        Issuer(
            _token,
            _hoursPerPeriod,
            _miningCoefficient,
            _lockedPeriodsCoefficient,
            _awardedPeriods
        )
    {
        require(_minLockedPeriods != 0 && _maxAllowableLockedTokens != 0);
        minLockedPeriods = _minLockedPeriods;
        minAllowableLockedTokens = _minAllowableLockedTokens;
        maxAllowableLockedTokens = _maxAllowableLockedTokens;
    }

    /**
    * @dev Checks that sender exists in contract
    **/
    modifier onlyTokenOwner()
    {
        require(minerInfo[msg.sender].value > 0);
        _;
    }

    /**
    * @notice Get the period to use in the calculation of the last period of the stake
    **/
    function getStartPeriod(MinerInfo storage _info, uint256 _currentPeriod)
        internal view returns (uint256)
    {
        // TODO try to optimize working with confirmed next period (getLockedTokens, lock, divideStake, mint)
        // if next period (after current) is confirmed
        if (_info.confirmedPeriod1 > _currentPeriod || _info.confirmedPeriod2 > _currentPeriod) {
            return _currentPeriod.add(uint256(1));
        }
        return _currentPeriod;
    }

    /**
    * @notice Get the last period of the stake
    **/
    function getLastPeriod(StakeInfo storage _stake, uint256 _startPeriod)
        internal view returns (uint256)
    {
        return _stake.lastPeriod != 0 ? _stake.lastPeriod : _startPeriod.add(_stake.periods);
    }

    /**
    * @notice Get locked tokens value for owner in current period
    * @param _owner Tokens owner
    **/
    function getLockedTokens(address _owner, uint256 _periods)
        public view returns (uint256 lockedValue)
    {
        uint256 startPeriod = getCurrentPeriod();
        uint256 nextPeriod = startPeriod.add(_periods);
        MinerInfo storage info = minerInfo[_owner];
        startPeriod = getStartPeriod(info, startPeriod);

        for (uint256 i = 0; i < info.stakes.length; i++) {
            StakeInfo storage stake = info.stakes[i];
            if (stake.firstPeriod <= nextPeriod &&
                getLastPeriod(stake, startPeriod) >= nextPeriod) {
                lockedValue = lockedValue.add(stake.lockedValue);
            }
        }
    }

    /**
    * @notice Get locked tokens value for owner in future period
    * @param _owner Tokens owner
    **/
    function getLockedTokens(address _owner)
        public view returns (uint256)
    {
        return getLockedTokens(_owner, 0);
    }

    /**
    * @notice Get locked tokens value for all owners in current period
    **/
    function getAllLockedTokens() public view returns (uint256) {
        return lockedPerPeriod[getCurrentPeriod()];
    }

    /**
    * @notice Pre-deposit tokens
    * @param _miners Tokens owners
    * @param _values Amount of token to deposit for each owner
    * @param _periods Amount of periods during which tokens will be unlocked for each owner
    **/
    function preDeposit(address[] _miners, uint256[] _values, uint256[] _periods)
        public isInitialized
    {
        require(_miners.length != 0 &&
            _miners.length == _values.length &&
            _miners.length == _periods.length);
        uint256 currentPeriod = getCurrentPeriod();
        uint256 allValue = 0;

        for (uint256 i = 0; i < _miners.length; i++) {
            address miner = _miners[i];
            uint256 value = _values[i];
            uint256 periods = _periods[i];
            MinerInfo storage info = minerInfo[miner];
            require(info.value == 0 &&
                value >= minAllowableLockedTokens &&
                value <= maxAllowableLockedTokens &&
                periods >= minLockedPeriods);
            miners.push(miner);
            info.lastActivePeriod = currentPeriod;
            info.value = value;
            info.stakes.push(StakeInfo(currentPeriod.add(uint256(1)), 0, periods, value));
            allValue = allValue.add(value);
            emit Deposited(miner, value, periods);
        }

        token.safeTransferFrom(msg.sender, address(this), allValue);
    }

    /**
    * @notice Implementation of the receiveApproval(address,uint256,address,bytes) method
    * (see NuCypherToken contract). Deposit all tokens that were approved to transfer
    * @param _from Tokens owner
    * @param _value Amount of token to deposit
    * @param _tokenContract Token contract address
    * @param _extraData Extra data - amount of periods during which tokens will be locked
    **/
    function receiveApproval(
        address _from,
        uint256 _value,
        address _tokenContract,
        bytes _extraData
    )
        external
    {
        require(_tokenContract == address(token) && msg.sender == address(token));
        // copy first 32 bytes from _extraData. Position is calculated as
        // 4 bytes method signature plus 32 * 3 bytes for previous params and
        // addition 32 bytes to skip _extraData pointer
        uint256 payloadSize;
        uint256 payload;
        assembly {
            payloadSize := calldataload(0x84)
            payload := calldataload(0xA4)
        }
        payload = payload >> 8*(32 - payloadSize);
        deposit(_from, _value, payload);
    }

    /**
    * @notice Deposit tokens
    * @param _value Amount of token to deposit
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function deposit(uint256 _value, uint256 _periods) public {
        deposit(msg.sender, _value, _periods);
    }

    /**
    * @notice Deposit tokens
    * @param _owner Tokens owner
    * @param _value Amount of token to deposit
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function deposit(address _owner, uint256 _value, uint256 _periods) internal isInitialized {
        require(_value != 0);
        MinerInfo storage info = minerInfo[_owner];
        if (info.lastActivePeriod == 0) {
            miners.push(_owner);
            info.lastActivePeriod = getCurrentPeriod();
        }
        info.value = info.value.add(_value);
        token.safeTransferFrom(_owner, address(this), _value);
        lock(_owner, _value, _periods);
        emit Deposited(_owner, _value, _periods);
    }

    /**
    * @notice Lock some tokens or increase lock
    * @param _value Amount of tokens which should lock
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function lock(uint256 _value, uint256 _periods) public onlyTokenOwner {
        lock(msg.sender, _value, _periods);
    }

    /**
    * @notice Lock some tokens or increase lock
    * @param _owner Tokens owner
    * @param _value Amount of tokens which should lock
    * @param _periods Amount of periods during which tokens will be locked
    **/
    function lock(address _owner, uint256 _value, uint256 _periods) internal {
        require(_value != 0 || _periods != 0);
        mint(_owner);

        uint256 lockedTokens = getLockedTokens(_owner, 1);
        MinerInfo storage info = minerInfo[_owner];
        require(_value <= token.balanceOf(address(this)) &&
            _value <= info.value.sub(lockedTokens) &&
            _value >= minAllowableLockedTokens &&
            _value.add(lockedTokens) <= maxAllowableLockedTokens &&
            _periods >= minLockedPeriods);

        uint256 nextPeriod = getCurrentPeriod().add(uint256(1));
        if (info.confirmedPeriod1 != nextPeriod && info.confirmedPeriod2 != nextPeriod) {
            info.stakes.push(StakeInfo(nextPeriod, 0, _periods, _value));
        } else {
            if (_periods == 1) {
                info.stakes.push(StakeInfo(nextPeriod, nextPeriod, 0, _value));
            } else {
                info.stakes.push(StakeInfo(nextPeriod, 0, _periods - 1, _value));
            }
        }

        confirmActivity(_owner, _value + lockedTokens, _value);
        emit Locked(_owner, _value, nextPeriod, _periods);
    }

    /**
    * @notice Divide stake into two parts
    * @param _oldValue Old stake value
    * @param _lastPeriod Last period of stake
    * @param _newValue New stake value
    * @param _periods Amount of periods for extending stake
    **/
    function divideStake(
        uint256 _oldValue,
        uint256 _lastPeriod,
        uint256 _newValue,
        uint256 _periods
    )
        public onlyTokenOwner
    {
        require(_newValue >= minAllowableLockedTokens && _periods > 0);
        MinerInfo storage info = minerInfo[msg.sender];
        uint256 startPeriod = getStartPeriod(info, getCurrentPeriod());
        for (uint256 index = 0; index < info.stakes.length; index++) {
            StakeInfo storage stake = info.stakes[index];
            uint256 lastPeriod = getLastPeriod(stake, startPeriod);
            if (stake.lockedValue == _oldValue &&
                lastPeriod == _lastPeriod) {
                break;
            }
        }
        // TODO lastPeriod can be equal current period (if next is confirmed) but need to recalculate in confirmActivity
        require(index < info.stakes.length && lastPeriod >= startPeriod);
        stake.lockedValue = stake.lockedValue.sub(_newValue);
        require(stake.lockedValue >= minAllowableLockedTokens);
        info.stakes.push(StakeInfo(stake.firstPeriod, 0, stake.periods.add(_periods), _newValue));
        emit Divided(msg.sender, _oldValue, _lastPeriod, _newValue, _periods);
        emit Locked(msg.sender, _newValue, stake.firstPeriod, stake.periods + _periods);
    }

    /**
    * @notice Withdraw available amount of tokens back to owner
    * @param _value Amount of token to withdraw
    **/
    function withdraw(uint256 _value) public onlyTokenOwner {
        MinerInfo storage info = minerInfo[msg.sender];
        // TODO optimize
        uint256 lockedTokens = Math.max256(getLockedTokens(msg.sender, 1),
            getLockedTokens(msg.sender, 0));
        require(_value <= token.balanceOf(address(this)) &&
            _value <= info.value.sub(lockedTokens));
        info.value -= _value;
        token.safeTransfer(msg.sender, _value);
        emit Withdrawn(msg.sender, _value);
    }

    /**
    * @notice Confirm activity for future period
    * @param _owner Tokens owner
    * @param _lockedValue Locked tokens in future period
    * @param _additional Additional locked tokens in future period.
    * Used only if the period has already been confirmed
    **/
    function confirmActivity(address _owner, uint256 _lockedValue, uint256 _additional) internal {
        require(_lockedValue > 0);
        MinerInfo storage info = minerInfo[_owner];
        uint256 nextPeriod = getCurrentPeriod() + 1;

        // update lockedValue if the period has already been confirmed
        if (info.confirmedPeriod1 == nextPeriod) {
            lockedPerPeriod[nextPeriod] = lockedPerPeriod[nextPeriod].add(_additional);
            emit ActivityConfirmed(_owner, nextPeriod, _additional);
            return;
        } else if (info.confirmedPeriod2 == nextPeriod) {
            lockedPerPeriod[nextPeriod] = lockedPerPeriod[nextPeriod].add(_additional);
            emit ActivityConfirmed(_owner, nextPeriod, _additional);
            return;
        }

        lockedPerPeriod[nextPeriod] = lockedPerPeriod[nextPeriod].add(_lockedValue);
        if (info.confirmedPeriod1 == EMPTY_CONFIRMED_PERIOD) {
            info.confirmedPeriod1 = nextPeriod;
        } else {
            info.confirmedPeriod2 = nextPeriod;
        }

        for (uint256 index = 0; index < info.stakes.length; index++) {
            StakeInfo storage stake = info.stakes[index];
            if (stake.periods > 1) {
                stake.periods--;
            } else if (stake.periods == 1) {
                stake.periods = 0;
                stake.lastPeriod = nextPeriod;
            }
        }

        uint256 currentPeriod = nextPeriod - 1;
        if (info.lastActivePeriod < currentPeriod) {
            info.downtime.push(Downtime(info.lastActivePeriod + 1, currentPeriod));
        }
        info.lastActivePeriod = nextPeriod;
        emit ActivityConfirmed(_owner, nextPeriod, _lockedValue);
    }

    /**
    * @notice Confirm activity for future period and mine for previous period
    **/
    function confirmActivity() external onlyTokenOwner {
        mint(msg.sender);
        MinerInfo storage info = minerInfo[msg.sender];
        uint256 currentPeriod = getCurrentPeriod();
        uint256 nextPeriod = currentPeriod + 1;

        // the period has already been confirmed
        if (info.confirmedPeriod1 == nextPeriod ||
            info.confirmedPeriod2 == nextPeriod) {
            return;
        }

        uint256 lockedTokens = getLockedTokens(msg.sender, 1);
        confirmActivity(msg.sender, lockedTokens, 0);
    }

    /**
    * @notice Mint tokens for sender for previous periods if he locked his tokens and confirmed activity
    **/
    function mint() public onlyTokenOwner {
        mint(msg.sender);
    }

    /**
    * @notice Mint tokens for owner for previous periods if he locked his tokens and confirmed activity
    * @param _owner Tokens owner
    **/
    function mint(address _owner) internal {
        uint256 startPeriod = getCurrentPeriod();
        uint256 previousPeriod = startPeriod.sub(uint(1));
        MinerInfo storage info = minerInfo[_owner];

        if (info.confirmedPeriod1 > previousPeriod &&
            info.confirmedPeriod2 > previousPeriod ||
            info.confirmedPeriod1 > previousPeriod &&
            info.confirmedPeriod2 == EMPTY_CONFIRMED_PERIOD ||
            info.confirmedPeriod2 > previousPeriod &&
            info.confirmedPeriod1 == EMPTY_CONFIRMED_PERIOD ||
            info.confirmedPeriod1 == EMPTY_CONFIRMED_PERIOD &&
            info.confirmedPeriod2 == EMPTY_CONFIRMED_PERIOD) {
            return;
        }

        uint256 first;
        uint256 last;
        if (info.confirmedPeriod1 > info.confirmedPeriod2) {
            last = info.confirmedPeriod1;
            first = info.confirmedPeriod2;
        } else {
            first = info.confirmedPeriod1;
            last = info.confirmedPeriod2;
        }

        startPeriod = getStartPeriod(info, startPeriod);
        uint256 reward = 0;
        if (info.confirmedPeriod1 != EMPTY_CONFIRMED_PERIOD &&
            info.confirmedPeriod1 < info.confirmedPeriod2) {
            reward = reward.add(mint(_owner, info, info.confirmedPeriod1, previousPeriod, startPeriod));
            info.confirmedPeriod1 = EMPTY_CONFIRMED_PERIOD;
        } else if (info.confirmedPeriod2 != EMPTY_CONFIRMED_PERIOD &&
            info.confirmedPeriod2 < info.confirmedPeriod1) {
            reward = reward.add(mint(_owner, info, info.confirmedPeriod2, previousPeriod, startPeriod));
            info.confirmedPeriod2 = EMPTY_CONFIRMED_PERIOD;
        }
        if (info.confirmedPeriod2 <= previousPeriod &&
            info.confirmedPeriod2 > info.confirmedPeriod1) {
            reward = reward.add(mint(_owner, info, info.confirmedPeriod2, previousPeriod, startPeriod));
            info.confirmedPeriod2 = EMPTY_CONFIRMED_PERIOD;
        } else if (info.confirmedPeriod1 <= previousPeriod &&
            info.confirmedPeriod1 > info.confirmedPeriod2) {
            reward = reward.add(mint(_owner, info, info.confirmedPeriod1, previousPeriod, startPeriod));
            info.confirmedPeriod1 = EMPTY_CONFIRMED_PERIOD;
        }

        info.value = info.value.add(reward);
        emit Mined(_owner, previousPeriod, reward);
    }

    /**
    * @notice Calculate reward for one period
    **/
    function mint(
        address _owner,
        MinerInfo storage _info,
        uint256 _period,
        uint256 _previousPeriod,
        uint256 _startPeriod
    )
        internal returns (uint256 reward)
    {
        uint256 amount;
        for (uint256 i = 0; i < _info.stakes.length; i++) {
            StakeInfo storage stake =  _info.stakes[i];
            uint256 lastPeriod = getLastPeriod(stake, _startPeriod);
            if (stake.firstPeriod <= _period && lastPeriod >= _period) {
                (amount, _info.decimals) = mint(
                    _previousPeriod,
                    stake.lockedValue,
                    lockedPerPeriod[_period],
                    lastPeriod.sub(_period),
                    _info.decimals);
                reward = reward.add(amount);
            }
        }
        policyManager.updateReward(_owner, _period);
    }

    /**
    * @notice Fixed-step in cumulative sum
    * @param _startIndex Starting point
    * @param _delta How much to step
    * @param _periods Amount of periods to get locked tokens
    *
             _startIndex
                v
      |-------->*--------------->*---->*------------->|
                |                      ^
                |                      stopIndex
                |
                |       _delta
                |---------------------------->|
                |
                |                       shift
                |                      |----->|
    **/
    function findCumSum(uint256 _startIndex, uint256 _delta, uint256 _periods)
        external view returns (address stop, uint256 stopIndex, uint256 shift)
    {
        require(_periods > 0);
        uint256 currentPeriod = getCurrentPeriod();
        uint256 distance = 0;

        for (uint256 i = _startIndex; i < miners.length; i++) {
            address current = miners[i];
            MinerInfo storage info = minerInfo[current];
            if (info.confirmedPeriod1 != currentPeriod &&
                info.confirmedPeriod2 != currentPeriod) {
                continue;
            }
            uint256 lockedTokens = getLockedTokens(current, _periods);
            if (_delta < distance.add(lockedTokens)) {
                stop = current;
                stopIndex = i;
                shift = _delta - distance;
                break;
            } else {
                distance += lockedTokens;
            }
        }
    }

    /**
    * @notice Set policy manager address
    **/
    function setPolicyManager(PolicyManagerInterface _policyManager) external onlyOwner {
        require(address(policyManager) == 0x0 &&
            _policyManager.escrow() == address(this));
        policyManager = _policyManager;
    }

    /**
    * @notice Return the length of the miner ids array
    **/
    function getMinerIdsLength(address _miner) public view returns (uint256) {
        return minerInfo[_miner].minerIds.length;
    }

    /**
    * @notice Return the miner id
    **/
    function getMinerId(address _miner, uint256 _index) public view returns (bytes32) {
        return minerInfo[_miner].minerIds[_index];
    }

    /**
    * @notice Set the miner id
    **/
    function setMinerId(bytes32 _minerId) public {
        MinerInfo storage info = minerInfo[msg.sender];
        info.minerIds.push(_minerId);
    }

    /**
    * @notice Return the length of the miners array
    **/
    function getMinersLength() public view returns (uint256) {
        return miners.length;
    }

    /**
    * @notice Return the length of the stakes array
    **/
    function getStakesLength(address _miner) public view returns (uint256) {
        return minerInfo[_miner].stakes.length;
    }

    /**
    * @notice Return the information about stake
    **/
    function getStakeInfo(address _miner, uint256 _index)
    // TODO change to structure when ABIEncoderV2 is released
//        public view returns (StakeInfo)
        public view returns (uint256 firstPeriod, uint256 lastPeriod, uint256 periods,uint256 lockedValue)
    {
        StakeInfo storage info = minerInfo[_miner].stakes[_index];
        firstPeriod = info.firstPeriod;
        lastPeriod = info.lastPeriod;
        periods = info.periods;
        lockedValue = info.lockedValue;
    }

    /**
    * @notice Return the length of the downtime array
    **/
    function getDowntimeLength(address _miner) public view returns (uint256) {
        return minerInfo[_miner].downtime.length;
    }

    /**
    * @notice Return the information about downtime
    **/
    function getDowntime(address _miner, uint256 _index)
    // TODO change to structure when ABIEncoderV2 is released
//        public view returns (Downtime)
        public view returns (uint256 startPeriod, uint256 endPeriod)
    {
        Downtime storage downtime = minerInfo[_miner].downtime[_index];
        startPeriod = downtime.startPeriod;
        endPeriod = downtime.endPeriod;
    }

    /**
    * @dev Get MinerInfo structure by delegatecall
    **/
    function delegateGetMinerInfo(address _target, address _miner)
        internal returns (MinerInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(_target, "minerInfo(address)", 1, bytes32(_miner), 0);
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get StakeInfo structure by delegatecall
    **/
    function delegateGetStakeInfo(address _target, address _miner, uint256 _index)
        internal returns (StakeInfo memory result)
    {
        bytes32 memoryAddress = delegateGetData(
            _target, "getStakeInfo(address,uint256)", 2, bytes32(_miner), bytes32(_index));
        assembly {
            result := memoryAddress
        }
    }

    /**
    * @dev Get Downtime structure by delegatecall
    **/
    function delegateGetDowntime(address _target, address _miner, uint256 _index)
        internal returns (Downtime memory result)
    {
        bytes32 memoryAddress = delegateGetData(
            _target, "getDowntime(address,uint256)", 2, bytes32(_miner), bytes32(_index));
        assembly {
            result := memoryAddress
        }
    }

    function verifyState(address _testTarget) public onlyOwner {
        super.verifyState(_testTarget);
        require(uint256(delegateGet(_testTarget, "minLockedPeriods()")) ==
            minLockedPeriods);
        require(uint256(delegateGet(_testTarget, "minAllowableLockedTokens()")) ==
            minAllowableLockedTokens);
        require(uint256(delegateGet(_testTarget, "maxAllowableLockedTokens()")) ==
            maxAllowableLockedTokens);
        require(address(delegateGet(_testTarget, "policyManager()")) == address(policyManager));
        require(uint256(delegateGet(_testTarget, "lockedPerPeriod(uint256)",
            bytes32(RESERVED_PERIOD))) == lockedPerPeriod[RESERVED_PERIOD]);

        require(uint256(delegateGet(_testTarget, "getMinersLength()")) == miners.length);
        if (miners.length == 0) {
            return;
        }
        address minerAddress = miners[0];
        bytes32 miner = bytes32(minerAddress);
        require(address(delegateGet(_testTarget, "miners(uint256)", 0)) == minerAddress);
        MinerInfo storage info = minerInfo[minerAddress];
        MinerInfo memory infoToCheck = delegateGetMinerInfo(_testTarget, minerAddress);
        require(infoToCheck.value == info.value &&
            infoToCheck.decimals == info.decimals &&
            infoToCheck.confirmedPeriod1 == info.confirmedPeriod1 &&
            infoToCheck.confirmedPeriod2 == info.confirmedPeriod2 &&
            infoToCheck.lastActivePeriod == info.lastActivePeriod);

        require(uint256(delegateGet(_testTarget, "getDowntimeLength(address)", miner)) == info.downtime.length);
        for (i = 0; i < info.downtime.length && i < MAX_CHECKED_VALUES; i++) {
            Downtime storage downtime = info.downtime[i];
            Downtime memory downtimeToCheck = delegateGetDowntime(_testTarget, minerAddress, i);
            require(downtimeToCheck.startPeriod == downtime.startPeriod &&
                downtimeToCheck.endPeriod == downtime.endPeriod);
        }

        require(uint256(delegateGet(_testTarget, "getStakesLength(address)", miner)) == info.stakes.length);
        for (uint256 i = 0; i < info.stakes.length && i < MAX_CHECKED_VALUES; i++) {
            StakeInfo storage stakeInfo = info.stakes[i];
            StakeInfo memory stakeInfoToCheck = delegateGetStakeInfo(_testTarget, minerAddress, i);
            require(stakeInfoToCheck.firstPeriod == stakeInfo.firstPeriod &&
                stakeInfoToCheck.lastPeriod == stakeInfo.lastPeriod &&
                stakeInfoToCheck.periods == stakeInfo.periods &&
                stakeInfoToCheck.lockedValue == stakeInfo.lockedValue);
        }

        require(uint256(delegateGet(_testTarget, "getMinerIdsLength(address)", miner)) == info.minerIds.length);
        for (i = 0; i < info.minerIds.length && i < MAX_CHECKED_VALUES; i++) {
            require(delegateGet(_testTarget, "getMinerId(address,uint256)", miner, bytes32(i)) == info.minerIds[i]);
        }
    }

    function finishUpgrade(address _target) public onlyOwner {
        super.finishUpgrade(_target);
        MinersEscrow escrow = MinersEscrow(_target);
        minLockedPeriods = escrow.minLockedPeriods();
        minAllowableLockedTokens = escrow.minAllowableLockedTokens();
        maxAllowableLockedTokens = escrow.maxAllowableLockedTokens();

        // Create fake period
        lockedPerPeriod[RESERVED_PERIOD] = 111;
    }
}
