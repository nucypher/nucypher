pragma solidity ^0.4.18;


import "contracts/NuCypherKMSToken.sol";
import "zeppelin/math/SafeMath.sol";
import "proxy/Upgradeable.sol";


/**
* @notice Contract for calculate issued tokens
**/
contract Issuer is Upgradeable {
    using SafeMath for uint256;

    /// Issuer is initialized with a reserved reward
    event Initialized(uint256 reservedReward);

    NuCypherKMSToken public token;
    uint256 public miningCoefficient;
    uint256 public secondsPerPeriod;
    uint256 public lockedPeriodsCoefficient;
    uint256 public awardedPeriods;

    uint256 public lastMintedPeriod;
    mapping (byte => uint256) public totalSupply;
    byte public currentIndex;
    uint256 public futureSupply;

    byte constant NEGATION = 0xF0;

    /**
    * @notice Constructor sets address of token contract and coefficients for mining
    * @dev Formula for mining in one period
    (futureSupply - currentSupply) * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / k2
    if allLockedPeriods > awardedPeriods then allLockedPeriods = awardedPeriods
    * @param _token Token contract
    * @param _hoursPerPeriod Size of period in hours
    * @param _miningCoefficient Mining coefficient (k2)
    * @param _lockedPeriodsCoefficient Locked blocks coefficient (k1)
    * @param _awardedPeriods Max periods that will be additionally awarded
    **/
    function Issuer(
        NuCypherKMSToken _token,
        uint256 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint256 _awardedPeriods
    )
        public
    {
        require(address(_token) != 0x0 &&
            _miningCoefficient != 0 &&
            _hoursPerPeriod != 0 &&
            _lockedPeriodsCoefficient != 0 &&
            _awardedPeriods != 0);
        token = _token;
        miningCoefficient = _miningCoefficient;
        secondsPerPeriod = _hoursPerPeriod.mul(1 hours);
        lockedPeriodsCoefficient = _lockedPeriodsCoefficient;
        awardedPeriods = _awardedPeriods;

        lastMintedPeriod = getCurrentPeriod();
        futureSupply = token.totalSupply();
    }

    /**
    * @dev Checks miner initialization
    **/
    modifier isInitialized()
    {
        require(currentIndex != 0x00);
        _;
    }

    /**
    * @return Number of current period
    **/
    function getCurrentPeriod() public view returns (uint256) {
        return block.timestamp / secondsPerPeriod;
    }

    /**
    * @notice Initialize reserved tokens for reward
    **/
    function initialize() public {
        require(currentIndex == 0x00);
        currentIndex = 0x01;
        uint256 reservedReward = token.balanceOf(address(this));
        uint256 currentTotalSupply = futureSupply.sub(reservedReward);
        totalSupply[currentIndex] = currentTotalSupply;
        totalSupply[currentIndex ^ NEGATION] = currentTotalSupply;
        Initialized(reservedReward);
    }

    /**
    * @notice Function to mint tokens for one period.
    * @param _period Period number.
    * @param _lockedValue The amount of tokens that were locked by user in specified period.
    * @param _totalLockedValue The amount of tokens that were locked by all users in specified period.
    * @param _allLockedPeriods The max amount of periods during which tokens will be locked after specified period.
    * @param _decimals The amount of locked tokens and blocks in decimals.
    * @return Amount of minted tokens.
    */
    // TODO decimals
    function mint(
        uint256 _period,
        uint256 _lockedValue,
        uint256 _totalLockedValue,
        uint256 _allLockedPeriods,
        uint256 _decimals
    )
        internal returns (uint256 amount, uint256 decimals)
    {
        // TODO end of mining before calculation
        uint256 nextTotalSupply = totalSupply[currentIndex ^ NEGATION];
        if (_period > lastMintedPeriod) {
            currentIndex = currentIndex ^ NEGATION;
            lastMintedPeriod = _period;
        }

        //futureSupply * lockedValue * (k1 + allLockedPeriods) / (totalLockedValue * k2) -
        //currentSupply * lockedValue * (k1 + allLockedPeriods) / (totalLockedValue * k2)
        uint256 allLockedPeriods = (_allLockedPeriods <= awardedPeriods ?
            _allLockedPeriods : awardedPeriods)
            .add(lockedPeriodsCoefficient);
        uint256 denominator = _totalLockedValue.mul(miningCoefficient);
        amount =
            futureSupply
                .mul(_lockedValue)
                .mul(allLockedPeriods)
                .div(denominator).sub(
            totalSupply[currentIndex]
                .mul(_lockedValue)
                .mul(allLockedPeriods)
                .div(denominator));
        decimals = _decimals;

        totalSupply[currentIndex ^ NEGATION] = nextTotalSupply.add(amount);
    }

    function verifyState(address _testTarget) public onlyOwner {
        require(address(delegateGet(_testTarget, "token()")) == address(token));
        require(uint256(delegateGet(_testTarget, "miningCoefficient()")) == miningCoefficient);
        require(uint256(delegateGet(_testTarget, "secondsPerPeriod()")) == secondsPerPeriod);
        require(uint256(delegateGet(_testTarget, "lockedPeriodsCoefficient()")) == lockedPeriodsCoefficient);
        require(uint256(delegateGet(_testTarget, "awardedPeriods()")) == awardedPeriods);
        require(uint256(delegateGet(_testTarget, "lastMintedPeriod()")) == lastMintedPeriod);
        require(byte(delegateGet(_testTarget, "currentIndex()")) == currentIndex);
        require(uint256(delegateGet(_testTarget, "totalSupply(bytes1)", currentIndex)) == totalSupply[currentIndex]);
        require(uint256(delegateGet(_testTarget, "totalSupply(bytes1)", currentIndex ^ NEGATION)) ==
            totalSupply[currentIndex ^ NEGATION]);
        require(uint256(delegateGet(_testTarget, "futureSupply()")) == futureSupply);
    }

    function finishUpgrade(address _target) public onlyOwner {
        Issuer issuer = Issuer(_target);
        token = issuer.token();
        miningCoefficient = issuer.miningCoefficient();
        secondsPerPeriod = issuer.secondsPerPeriod();
        lockedPeriodsCoefficient = issuer.lockedPeriodsCoefficient();
        awardedPeriods = issuer.awardedPeriods();

        lastMintedPeriod = issuer.lastMintedPeriod();
        futureSupply = issuer.futureSupply();
    }
}
