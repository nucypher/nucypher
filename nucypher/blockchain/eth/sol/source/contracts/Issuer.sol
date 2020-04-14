pragma solidity ^0.6.5;


import "contracts/NuCypherToken.sol";
import "zeppelin/math/SafeMath.sol";
import "zeppelin/math/Math.sol";
import "contracts/proxy/Upgradeable.sol";
import "contracts/lib/AdditionalMath.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";


/**
* @notice Contract for calculation of issued tokens
* @dev |v2.1.1|
*/
abstract contract Issuer is Upgradeable {
    using SafeERC20 for NuCypherToken;
    using SafeMath for uint256;
    using AdditionalMath for uint32;

    event Burnt(address indexed sender, uint256 value);
    /// Issuer is initialized with a reserved reward
    event Initialized(uint256 reservedReward);

    NuCypherToken public immutable token;
    uint256 public immutable totalSupply;

    uint256 public immutable miningCoefficient;
    uint256 public immutable lockedPeriodsCoefficient;
    uint32 public immutable secondsPerPeriod;
    uint16 public immutable rewardedPeriods;

    uint16 public currentMintingPeriod;
    /**
    * Current supply is used in the mining formula and is stored to prevent different calculation
    * for stakers which get reward in the same period. There are two values -
    * supply for previous period (used in formula) and supply for current period which accumulates value
    * before end of period. There is no order between them because of storage savings.
    * So each time should check values of both variables.
    */
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
    */
    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _miningCoefficient,
        uint256 _lockedPeriodsCoefficient,
        uint16 _rewardedPeriods
    )
        public
    {
        uint256 localTotalSupply = _token.totalSupply();
        require(localTotalSupply > 0 &&
            _miningCoefficient != 0 &&
            _hoursPerPeriod != 0 &&
            _lockedPeriodsCoefficient != 0 &&
            _rewardedPeriods != 0);
        uint256 maxLockedPeriods = _rewardedPeriods + _lockedPeriodsCoefficient;
        require(maxLockedPeriods > _rewardedPeriods &&
            // worst case for `totalLockedValue * k2`, when totalLockedValue == totalSupply
            localTotalSupply * _miningCoefficient / localTotalSupply == _miningCoefficient &&
            // worst case for `(totalSupply - currentSupply) * lockedValue * (k1 + allLockedPeriods)`,
            // when currentSupply == 0, lockedValue == totalSupply
            localTotalSupply * localTotalSupply * maxLockedPeriods / localTotalSupply / localTotalSupply == maxLockedPeriods,
            "Specified parameters cause overflow");
        token = _token;
        miningCoefficient = _miningCoefficient;
        secondsPerPeriod = _hoursPerPeriod.mul32(1 hours);
        lockedPeriodsCoefficient = _lockedPeriodsCoefficient;
        rewardedPeriods = _rewardedPeriods;
        totalSupply = localTotalSupply;
    }

    /**
    * @dev Checks contract initialization
    */
    modifier isInitialized()
    {
        require(currentMintingPeriod != 0);
        _;
    }

    /**
    * @return Number of current period
    */
    function getCurrentPeriod() public view returns (uint16) {
        return uint16(block.timestamp / secondsPerPeriod);
    }

    /**
    * @notice Initialize reserved tokens for reward
    */
    function initialize(uint256 _reservedReward) external onlyOwner {
        require(currentMintingPeriod == 0);
        token.safeTransferFrom(msg.sender, address(this), _reservedReward);
        currentMintingPeriod = getCurrentPeriod();
        uint256 currentTotalSupply = totalSupply - _reservedReward;
        currentSupply1 = currentTotalSupply;
        currentSupply2 = currentTotalSupply;
        emit Initialized(_reservedReward);
    }

    /**
    * @notice Function to mint tokens for one period.
    * @param _currentPeriod Current period number.
    * @param _lockedValue The amount of tokens that were locked by user in specified period.
    * @param _totalLockedValue The amount of tokens that were locked by all users in specified period.
    * @param _allLockedPeriods The max amount of periods during which tokens will be locked after specified period.
    * @return amount Amount of minted tokens.
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

        uint256 maxReward = getReservedReward();
        uint256 currentReward = _currentPeriod <= currentMintingPeriod ?
            totalSupply - Math.min(currentSupply1, currentSupply2) : maxReward;

        //(totalSupply - currentSupply) * lockedValue * (k1 + allLockedPeriods) / (totalLockedValue * k2)
        uint256 allLockedPeriods =
            AdditionalMath.min16(_allLockedPeriods, rewardedPeriods) + lockedPeriodsCoefficient;
        amount = (currentReward * _lockedValue * allLockedPeriods) /
            (_totalLockedValue * miningCoefficient);

        // rounding the last reward
        if (amount == 0) {
            amount = 1;
        } else if (amount > maxReward) {
            amount = maxReward;
        }

        if (_currentPeriod <= currentMintingPeriod) {
            if (currentSupply1 > currentSupply2) {
                currentSupply1 += amount;
            } else {
                currentSupply2 += amount;
            }
        } else {
            currentMintingPeriod = _currentPeriod;
            if (currentSupply1 > currentSupply2) {
                currentSupply2 = currentSupply1 + amount;
            } else {
                currentSupply1 = currentSupply2 + amount;
            }
        }
    }

    /**
    * @notice Return tokens for future minting
    * @param _amount Amount of tokens
    */
    function unMint(uint256 _amount) internal {
        currentSupply1 -= _amount;
        currentSupply2 -= _amount;
    }

    /**
    * @notice Burn sender's tokens. Amount of tokens will be returned for future minting
    * @param _value Amount to burn
    */
    function burn(uint256 _value) external isInitialized {
        token.safeTransferFrom(msg.sender, address(this), _value);
        unMint(_value);
        emit Burnt(msg.sender, _value);
    }

    /**
    * @notice Returns the number of tokens that can be mined
    */
    function getReservedReward() public view returns (uint256) {
        return totalSupply - Math.max(currentSupply1, currentSupply2);
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `verifyState`
    function verifyState(address _testTarget) public override virtual {
        super.verifyState(_testTarget);
        require(uint16(delegateGet(_testTarget, this.currentMintingPeriod.selector)) == currentMintingPeriod);
        require(delegateGet(_testTarget, this.currentSupply1.selector) == currentSupply1);
        require(delegateGet(_testTarget, this.currentSupply2.selector) == currentSupply2);
    }

}
