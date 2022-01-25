// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "threshold/IStaking.sol";


/**
* @title PRE Application
* @notice Contract handles PRE configuration
*/
contract SimplePREApplication {

    /**
    * @notice Signals that an operator was bonded to the staking provider
    * @param stakingProvider Staking provider address
    * @param operator Operator address
    * @param startTimestamp Timestamp bonding occurred
    */
    event OperatorBonded(address indexed stakingProvider, address indexed operator, uint256 startTimestamp);

    /**
    * @notice Signals that an operator address is confirmed
    * @param stakingProvider Staking provider address
    * @param operator Operator address
    */
    event OperatorConfirmed(address indexed stakingProvider, address indexed operator);

    struct StakingProviderInfo {
        address operator;
        bool operatorConfirmed;
        uint256 operatorStartTimestamp;
    }

    uint256 public immutable minAuthorization;
    uint256 public immutable minOperatorSeconds;

    IStaking public immutable tStaking;

    mapping (address => StakingProviderInfo) public stakingProviderInfo;
    address[] public stakingProviders;
    mapping(address => address) internal _stakingProviderFromOperator;


    /**
    * @notice Constructor sets address of token contract and parameters for staking
    * @param _tStaking T token staking contract
    * @param _minAuthorization Amount of minimum allowable authorization
    * @param _minOperatorSeconds Min amount of seconds while an operator can't be changed
    */
    constructor(
        IStaking _tStaking,
        uint256 _minAuthorization,
        uint256 _minOperatorSeconds
    ) {
        require(
            _tStaking.authorizedStake(address(this), address(this)) == 0,
            "Wrong input parameters"
        );
        minAuthorization = _minAuthorization;
        tStaking = _tStaking;
        minOperatorSeconds = _minOperatorSeconds;
    }

    /**
    * @dev Checks caller is a staking provider or stake owner
    */
    modifier onlyOwnerOrStakingProvider(address _stakingProvider)
    {
        require(isAuthorized(_stakingProvider), "Not owner or provider");
        if (_stakingProvider != msg.sender) {
            (address owner,,) = tStaking.rolesOf(_stakingProvider);
            require(owner == msg.sender, "Not owner or provider");
        }
        _;
    }


    //-------------------------Main-------------------------
    /**
    * @notice Returns staking provider for specified operator
    */
    function stakingProviderFromOperator(address _operator) public view returns (address) {
        return _stakingProviderFromOperator[_operator];
    }

    /**
    * @notice Returns operator for specified staking provider
    */
    function getOperatorFromStakingProvider(address _stakingProvider) public view returns (address) {
        return stakingProviderInfo[_stakingProvider].operator;
    }

    /**
    * @notice Get all tokens delegated to the staking provider
    */
    function authorizedStake(address _stakingProvider) public view returns (uint96) {
        (uint96 tStake, uint96 keepInTStake, uint96 nuInTStake) = tStaking.stakes(_stakingProvider);
        return tStake + keepInTStake + nuInTStake;
    }

    /**
    * @notice Get the value of authorized tokens for active providers as well as providers and their authorized tokens
    * @param _startIndex Start index for looking in providers array
    * @param _maxStakingProviders Max providers for looking, if set 0 then all will be used
    * @return allAuthorizedTokens Sum of authorized tokens for active providers
    * @return activeStakingProviders Array of providers and their authorized tokens.
    * Providers addresses stored as uint256
    * @dev Note that activeStakingProviders[0] is an array of uint256, but you want addresses.
    * Careful when used directly!
    */
    function getActiveStakingProviders(uint256 _startIndex, uint256 _maxStakingProviders)
        external view returns (uint256 allAuthorizedTokens, uint256[2][] memory activeStakingProviders)
    {
        uint256 endIndex = stakingProviders.length;
        require(_startIndex < endIndex, "Wrong start index");
        if (_maxStakingProviders != 0 && _startIndex + _maxStakingProviders < endIndex) {
            endIndex = _startIndex + _maxStakingProviders;
        }
        activeStakingProviders = new uint256[2][](endIndex - _startIndex);
        allAuthorizedTokens = 0;

        uint256 resultIndex = 0;
        for (uint256 i = _startIndex; i < endIndex; i++) {
            address stakingProvider = stakingProviders[i];
            StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
            uint256 eligibleAmount = authorizedStake(stakingProvider);
            if (eligibleAmount < minAuthorization || !info.operatorConfirmed) {
                continue;
            }
            activeStakingProviders[resultIndex][0] = uint256(uint160(stakingProvider));
            activeStakingProviders[resultIndex++][1] = eligibleAmount;
            allAuthorizedTokens += eligibleAmount;
        }
        assembly {
            mstore(activeStakingProviders, resultIndex)
        }
    }

    /**
    * @notice Returns beneficiary related to the staking provider
    */
    function getBeneficiary(address _stakingProvider) public view returns (address payable beneficiary) {
        (, beneficiary,) = tStaking.rolesOf(_stakingProvider);
    }

    /**
    * @notice Returns true if staking provider has authorized stake to this application
    */
    function isAuthorized(address _stakingProvider) public view returns (bool) {
        return authorizedStake(_stakingProvider) >= minAuthorization;
    }

    /**
    * @notice Returns true if operator has confirmed address
    */
    // TODO maybe _stakingProvider instead of _operator as input?
    function isOperatorConfirmed(address _operator) public view returns (bool) {
        address stakingProvider = _stakingProviderFromOperator[_operator];
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        return info.operatorConfirmed;
    }

    /**
    * @notice Return the length of the array of staking providers
    */
    function getStakingProvidersLength() external view returns (uint256) {
        return stakingProviders.length;
    }

    /**
    * @notice Bond operator
    * @param _stakingProvider Staking provider address
    * @param _operator Operator address. Must be a real address, not a contract
    */
    function bondOperator(address _stakingProvider, address _operator)
        external onlyOwnerOrStakingProvider(_stakingProvider)
    {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        require(_operator != info.operator, "Specified operator is already bonded with this provider");
        // If this staker had a operator ...
        if (info.operator != address(0)) {
            require(
                block.timestamp >= info.operatorStartTimestamp + minOperatorSeconds,
                "Not enough time passed to change operator"
            );
            // Remove the old relation "operator->stakingProvider"
            _stakingProviderFromOperator[info.operator] = address(0);
        }

        if (_operator != address(0)) {
            require(_stakingProviderFromOperator[_operator] == address(0), "Specified operator is already in use");
            require(
                _operator == _stakingProvider || getBeneficiary(_operator) == address(0),
                "Specified operator is a provider"
            );
            // Set new operator->stakingProvider relation
            _stakingProviderFromOperator[_operator] = _stakingProvider;
        }

        if (info.operatorStartTimestamp == 0) {
            stakingProviders.push(_stakingProvider);
        }

        // Bond new operator (or unbond if _operator == address(0))
        info.operator = _operator;
        info.operatorStartTimestamp = block.timestamp;
        info.operatorConfirmed = false;
        emit OperatorBonded(_stakingProvider, _operator, block.timestamp);
    }

    /**
    * @notice Make a confirmation by operator
    */
    function confirmOperatorAddress() external {
        address stakingProvider = _stakingProviderFromOperator[msg.sender];
        require(isAuthorized(stakingProvider), "No stake associated with the operator");
        StakingProviderInfo storage info = stakingProviderInfo[stakingProvider];
        require(!info.operatorConfirmed, "Operator address is already confirmed");
        require(msg.sender == tx.origin, "Only operator with real address can make a confirmation");
        info.operatorConfirmed = true;
        emit OperatorConfirmed(stakingProvider, msg.sender);
    }

}
