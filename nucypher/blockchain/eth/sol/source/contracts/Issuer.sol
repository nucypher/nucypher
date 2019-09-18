pragma solidity ^0.5.3;


import "contracts/NuCypherToken.sol";
import "zeppelin/math/SafeMath.sol";
import "zeppelin/math/Math.sol";
import "contracts/proxy/Upgradeable.sol";
import "contracts/lib/AdditionalMath.sol";


/**
* @notice Contract for calculate issued tokens
**/
contract Issuer is Upgradeable {
    using SafeMath for uint256;
    using AdditionalMath for uint32;

    /// Issuer is initialized with a reserved reward
    event Initialized(uint256 reservedReward);

    NuCypherToken public token;
    uint256 public miningCoefficient;
    uint256 public lockedPeriodsCoefficient;
    uint32 public secondsPerPeriod;
    uint16 public rewardedPeriods;

    uint16 public currentMintingPeriod;
    uint256 public totalSupply;
    /**
    * Current supply is used in the mining formula and is stored to prevent different calculation
    * for stakers which get reward in the same period. There are two values -
    * supply for previous period (used in formula) and supply for current period which accumulates value
    * before end of period. There is no order between them because of storage savings.
    * So each time should check values of both variables.
    **/
    uint256 public currentSupply1;
    uint256 public currentSupply2;

    /**
    * @notice Constructor sets address of token contract and coefficients for mining
    * @dev Mining formula for one stake in one period
    (totalSupply - currentSupply) * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / k2
    if allLockedPeriods > rewardedPeriods then allLockedPeriods = rewardedPeriods
    * @param _token Token contract
    * @param _hoursPerPeriod Size of period in hours
    * @param _miningCoefficient Mining coefficient (k2)
    * @param _lockedPeriodsCoefficient Locked periods coefficient (k1)
    * @param _rewardedPeriods Max periods that will be additionally rewarded
    **/
    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint16 _rewardedPeriods
    )
        public
    {
        require(_token.totalSupply() > 0 &&
            _miningCoefficient != 0 &&
            _hoursPerPeriod != 0 &&
            _lockedPeriodsCoefficient != 0 &&
            _rewardedPeriods != 0);
        token = _token;
        miningCoefficient = _miningCoefficient;
        secondsPerPeriod = _hoursPerPeriod.mul32(1 hours);
        lockedPeriodsCoefficient = _lockedPeriodsCoefficient;
        rewardedPeriods = _rewardedPeriods;
    }

    /**
    * @dev Checks contract initialization
    **/
    modifier isInitialized()
    {
        require(currentSupply1 != 0);
        _;
    }

    /**
    * @return Number of current period
    **/
    function getCurrentPeriod() public view returns (uint16) {
        return uint16(block.timestamp / secondsPerPeriod);
    }

    /**
    * @notice Initialize reserved tokens for reward
    **/
    function initialize() public onlyOwner {
        require(currentSupply1 == 0);
        currentMintingPeriod = getCurrentPeriod();
        totalSupply = token.totalSupply();
        uint256 reservedReward = token.balanceOf(address(this));
        uint256 currentTotalSupply = totalSupply.sub(reservedReward);
        currentSupply1 = currentTotalSupply;
        currentSupply2 = currentTotalSupply;
        emit Initialized(reservedReward);
    }

    /**
    * @notice Function to mint tokens for one period.
    * @param _currentPeriod Current period number.
    * @param _lockedValue The amount of tokens that were locked by user in specified period.
    * @param _totalLockedValue The amount of tokens that were locked by all users in specified period.
    * @param _allLockedPeriods The max amount of periods during which tokens will be locked after specified period.
    * @return Amount of minted tokens.
    */
    function mint(
        uint16 _currentPeriod,
        uint256 _lockedValue,
        uint256 _totalLockedValue,
        uint16 _allLockedPeriods
    )
        internal returns (uint256 amount)
    {
        if (currentSupply1 == totalSupply || currentSupply2 == totalSupply) {
            return 0;
        }
        uint256 currentSupply = _currentPeriod <= currentMintingPeriod ?
            Math.min(currentSupply1, currentSupply2) :
            Math.max(currentSupply1, currentSupply2);

        //(totalSupply - currentSupply) * lockedValue * (k1 + allLockedPeriods) / (totalLockedValue * k2)
        uint256 allLockedPeriods = uint256(_allLockedPeriods <= rewardedPeriods ?
            _allLockedPeriods : rewardedPeriods)
            .add(lockedPeriodsCoefficient);
        uint256 denominator = _totalLockedValue.mul(miningCoefficient);
        amount = totalSupply.sub(currentSupply)
                            .mul(_lockedValue)
                            .mul(allLockedPeriods)
                            .div(denominator);
        // rounding the last reward
        if (amount == 0) {
            amount = 1;
        }

        if (_currentPeriod <= currentMintingPeriod) {
            if (currentSupply1 > currentSupply2) {
                currentSupply1 = currentSupply1.add(amount);
            } else {
                currentSupply2 = currentSupply2.add(amount);
            }
        } else {
            currentMintingPeriod = _currentPeriod;
            if (currentSupply1 > currentSupply2) {
                currentSupply2 = currentSupply1.add(amount);
            } else {
                currentSupply1 = currentSupply2.add(amount);
            }
        }
    }

    /**
    * @notice Return tokens for future minting
    * @param _amount Amount of tokens
    **/
    function unMint(uint256 _amount) internal {
        currentSupply1 = currentSupply1.sub(_amount);
        currentSupply2 = currentSupply2.sub(_amount);
    }

    /**
    * @notice Returns the number of tokens that can be mined
    **/
    function getReservedReward() public view returns (uint256) {
        return totalSupply - Math.max(currentSupply1, currentSupply2);
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `verifyState`
    function verifyState(address _testTarget) public {
        super.verifyState(_testTarget);
        require(address(uint160(delegateGet(_testTarget, "token()"))) == address(token));
        require(delegateGet(_testTarget, "miningCoefficient()") == miningCoefficient);
        require(delegateGet(_testTarget, "lockedPeriodsCoefficient()") == lockedPeriodsCoefficient);
        require(uint32(delegateGet(_testTarget, "secondsPerPeriod()")) == secondsPerPeriod);
        require(uint16(delegateGet(_testTarget, "rewardedPeriods()")) == rewardedPeriods);
        require(uint16(delegateGet(_testTarget, "currentMintingPeriod()")) == currentMintingPeriod);
        require(delegateGet(_testTarget, "currentSupply1()") == currentSupply1);
        require(delegateGet(_testTarget, "currentSupply2()") == currentSupply2);
        require(delegateGet(_testTarget, "totalSupply()") == totalSupply);
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `finishUpgrade`
    function finishUpgrade(address _target) public {
        super.finishUpgrade(_target);
        Issuer issuer = Issuer(_target);
        token = issuer.token();
        miningCoefficient = issuer.miningCoefficient();
        secondsPerPeriod = issuer.secondsPerPeriod();
        lockedPeriodsCoefficient = issuer.lockedPeriodsCoefficient();
        rewardedPeriods = issuer.rewardedPeriods();
    }
}
