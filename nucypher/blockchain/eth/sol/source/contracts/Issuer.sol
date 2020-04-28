pragma solidity ^0.6.5;


import "contracts/NuCypherToken.sol";
import "zeppelin/math/Math.sol";
import "contracts/proxy/Upgradeable.sol";
import "contracts/lib/AdditionalMath.sol";
import "zeppelin/token/ERC20/SafeERC20.sol";


/**
* @notice Contract for calculation of issued tokens
* @dev |v3.2.1|
*/
abstract contract Issuer is Upgradeable {
    using SafeERC20 for NuCypherToken;
    using AdditionalMath for uint32;

    event Burnt(address indexed sender, uint256 value);
    /// Issuer is initialized with a reserved reward
    event Initialized(uint256 reservedReward);

    uint128 constant MAX_UINT128 = uint128(0) - 1;

    NuCypherToken public immutable token;
    uint128 public immutable totalSupply;

    // k2 * k3
    uint256 public immutable mintingCoefficient;
    // k1
    uint256 public immutable lockingDurationCoefficient1;
    // k3
    uint256 public immutable lockingDurationCoefficient2;
    uint32 public immutable secondsPerPeriod;
    uint16 public immutable maxRewardedPeriods;

    uint256 public immutable maxFirstPhaseReward;
    uint256 public immutable firstPhaseTotalSupply;

    /**
    * Current supply is used in the minting formula and is stored to prevent different calculation
    * for stakers which get reward in the same period. There are two values -
    * supply for previous period (used in formula) and supply for current period which accumulates value
    * before end of period.
    */
    uint128 public previousPeriodSupply;
    uint128 public currentPeriodSupply;
    uint16 public currentMintingPeriod;

    /**
    * @notice Constructor sets address of token contract and coefficients for minting
    * @dev Minting formula for one sub-stake in one period for the first phase
    maxFirstPhaseReward * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / k3
    * @dev Minting formula for one sub-stake in one period for the seconds phase
    (totalSupply - currentSupply) / k2 * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / k3
    if allLockedPeriods > maxRewardedPeriods then allLockedPeriods = maxRewardedPeriods
    * @param _token Token contract
    * @param _hoursPerPeriod Size of period in hours
    * @param _secondPhaseMintingCoefficient Minting coefficient for the second phase (k2)
    * @param _lockingDurationCoefficient1 Numerator of the locking duration coefficient (k1)
    * @param _lockingDurationCoefficient2 Denominator of the locking duration coefficient (k3)
    * @param _maxRewardedPeriods Max periods that will be additionally rewarded
    * @param _firstPhaseTotalSupply Total supply for the first phase
    * @param _maxFirstPhaseReward Max possible reward for one period for all stakers in the first phase
    */
    constructor(
        NuCypherToken _token,
        uint32 _hoursPerPeriod,
        uint256 _secondPhaseMintingCoefficient,
        uint256 _lockingDurationCoefficient1,
        uint256 _lockingDurationCoefficient2,
        uint16 _maxRewardedPeriods,
        uint256 _firstPhaseTotalSupply,
        uint256 _maxFirstPhaseReward
    )
        public
    {
        uint256 localTotalSupply = _token.totalSupply();
        require(localTotalSupply > 0 &&
            _secondPhaseMintingCoefficient != 0 &&
            _hoursPerPeriod != 0 &&
            _lockingDurationCoefficient1 != 0 &&
            _lockingDurationCoefficient2 != 0 &&
            _maxRewardedPeriods != 0);
        require(localTotalSupply <= uint256(MAX_UINT128), "Token contract has supply more than supported");

        uint256 maxLockingDurationCoefficient = _maxRewardedPeriods + _lockingDurationCoefficient1;
        uint256 localMintingCoefficient = _secondPhaseMintingCoefficient * _lockingDurationCoefficient2;
        require(maxLockingDurationCoefficient > _maxRewardedPeriods &&
            localMintingCoefficient / _secondPhaseMintingCoefficient ==  _lockingDurationCoefficient2 &&
            // worst case for `totalLockedValue * k2 * k3`, when totalLockedValue == totalSupply
            localTotalSupply * localMintingCoefficient / localTotalSupply == localMintingCoefficient &&
            // worst case for `(totalSupply - currentSupply) * lockedValue * (k1 + allLockedPeriods)`,
            // when currentSupply == 0, lockedValue == totalSupply
            localTotalSupply * localTotalSupply * maxLockingDurationCoefficient / localTotalSupply / localTotalSupply ==
                maxLockingDurationCoefficient,
            "Specified parameters cause overflow");

        require(maxLockingDurationCoefficient <= _lockingDurationCoefficient2,
            "Resulting locking duration coefficient must be less than 1");
        require(_firstPhaseTotalSupply <= localTotalSupply, "Too many tokens for the first phase");
        require(_maxFirstPhaseReward <= _firstPhaseTotalSupply, "Reward for the first phase is too high");

        token = _token;
        secondsPerPeriod = _hoursPerPeriod.mul32(1 hours);
        lockingDurationCoefficient1 = _lockingDurationCoefficient1;
        lockingDurationCoefficient2 = _lockingDurationCoefficient2;
        maxRewardedPeriods = _maxRewardedPeriods;
        firstPhaseTotalSupply = _firstPhaseTotalSupply;
        maxFirstPhaseReward = _maxFirstPhaseReward;
        totalSupply = uint128(localTotalSupply);
        mintingCoefficient = localMintingCoefficient;
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
        // Reserved reward must be sufficient for at least one period of the first phase
        require(maxFirstPhaseReward <= _reservedReward);
        currentMintingPeriod = getCurrentPeriod();
        currentPeriodSupply = totalSupply - uint128(_reservedReward);
        previousPeriodSupply = currentPeriodSupply;
        token.safeTransferFrom(msg.sender, address(this), _reservedReward);
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
        if (currentPeriodSupply == totalSupply) {
            return 0;
        }

        if (_currentPeriod > currentMintingPeriod) {
            previousPeriodSupply = currentPeriodSupply;
            currentMintingPeriod = _currentPeriod;
        }

        uint256 currentReward;
        uint256 coefficient;

        // first phase
        // maxFirstPhaseReward * lockedValue * (k1 + allLockedPeriods) / (totalLockedValue * k3)
        if (previousPeriodSupply + maxFirstPhaseReward <= firstPhaseTotalSupply) {
            currentReward = maxFirstPhaseReward;
            coefficient = lockingDurationCoefficient2;
        // second phase
        // (totalSupply - currentSupply) * lockedValue * (k1 + allLockedPeriods) / (totalLockedValue * k2 * k3)
        } else {
            currentReward = totalSupply - previousPeriodSupply;
            coefficient = mintingCoefficient;
        }

        uint256 allLockedPeriods =
            AdditionalMath.min16(_allLockedPeriods, maxRewardedPeriods) + lockingDurationCoefficient1;
        amount = (uint256(currentReward) * _lockedValue * allLockedPeriods) /
            (_totalLockedValue * coefficient);

        // rounding the last reward
        // TODO optimize
        uint256 maxReward = getReservedReward();
        if (amount == 0) {
            amount = 1;
        } else if (amount > maxReward) {
            amount = maxReward;
        }

        currentPeriodSupply += uint128(amount);
    }

    /**
    * @notice Return tokens for future minting
    * @param _amount Amount of tokens
    */
    function unMint(uint256 _amount) internal {
        previousPeriodSupply -= uint128(_amount);
        currentPeriodSupply -= uint128(_amount);
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
        return totalSupply - currentPeriodSupply;
    }

    /// @dev the `onlyWhileUpgrading` modifier works through a call to the parent `verifyState`
    function verifyState(address _testTarget) public override virtual {
        super.verifyState(_testTarget);
        require(uint16(delegateGet(_testTarget, this.currentMintingPeriod.selector)) == currentMintingPeriod);
        require(uint128(delegateGet(_testTarget, this.previousPeriodSupply.selector)) == previousPeriodSupply);
        require(uint128(delegateGet(_testTarget, this.currentPeriodSupply.selector)) == currentPeriodSupply);
    }

}
