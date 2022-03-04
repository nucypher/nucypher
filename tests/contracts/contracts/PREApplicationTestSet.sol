// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "contracts/SimplePREApplication.sol";
//import "zeppelin/token/ERC20/ERC20.sol";
//import "zeppelin/token/ERC20/ERC20Detailed.sol";


///**
//* @notice Contract for testing PRE application contract
//*/
//contract TToken is ERC20, ERC20Detailed('T', 'T', 18) {
//
//    constructor (uint256 _totalSupplyOfTokens) {
//        _mint(msg.sender, _totalSupplyOfTokens);
//    }
//
//}


/**
* @notice Contract for testing PRE application contract
*/
contract ThresholdStakingForPREApplicationMock {

    struct StakingProviderInfo {
        address owner;
        address payable beneficiary;
        address authorizer;
        uint96 tStake;
        uint96 keepInTStake;
        uint96 nuInTStake;
    }

    SimplePREApplication public preApplication;

    mapping (address => StakingProviderInfo) public stakingProviderInfo;

    function setApplication(SimplePREApplication _preApplication) external {
        preApplication = _preApplication;
    }

    function stakedNu(address) external view returns (uint256) {
        return 0;
    }

    function setRoles(
        address _stakingProvider,
        address _owner,
        address payable _beneficiary,
        address _authorizer
    )
        external
    {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        info.owner = _owner;
        info.beneficiary = _beneficiary;
        info.authorizer = _authorizer;
    }

    /**
    * @dev If the function is called with only the _stakingProvider parameter,
    * we presume that the caller wants that address set for the other roles as well.
    */
    function setRoles(address _stakingProvider) external {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        info.owner = _stakingProvider;
        info.beneficiary = payable(_stakingProvider);
        info.authorizer = _stakingProvider;
    }

    function setStakes(
        address _stakingProvider,
        uint96 _tStake,
        uint96 _keepInTStake,
        uint96 _nuInTStake
    )
        external
    {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        info.tStake = _tStake;
        info.keepInTStake = _keepInTStake;
        info.nuInTStake = _nuInTStake;
    }

    function authorizedStake(address _stakingProvider, address _application) external view returns (uint96) {
        return 0;
    }

    function stakes(address _stakingProvider) external view returns (
        uint96 tStake,
        uint96 keepInTStake,
        uint96 nuInTStake
    ) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        tStake = info.tStake;
        keepInTStake = info.keepInTStake;
        nuInTStake = info.nuInTStake;
    }

    function rolesOf(address _stakingProvider) external view returns (
        address owner,
        address payable beneficiary,
        address authorizer
    ) {
        StakingProviderInfo storage info = stakingProviderInfo[_stakingProvider];
        owner = info.owner;
        beneficiary = info.beneficiary;
        authorizer = info.authorizer;
    }

//    function approveAuthorizationDecrease(address _stakingProvider) external returns (uint96) {
//
//    }

//    function seize(
//        uint96 _amount,
//        uint256 _rewardMultipier,
//        address _notifier,
//        address[] memory _stakingProviders
//    ) external {
//
//    }

//    function authorizationIncreased(address _stakingProvider, uint96 _fromAmount, uint96 _toAmount) external {
//        preApplication.authorizationIncreased(_stakingProvider, _fromAmount, _toAmount);
//    }

}


/**
* @notice Intermediary contract for testing operator
*/
contract Intermediary {

    SimplePREApplication immutable preApplication;

    constructor(SimplePREApplication _preApplication) {
        preApplication = _preApplication;
    }

    function bondOperator(address _operator) external {
        preApplication.bondOperator(address(this), _operator);
    }

    function confirmOperatorAddress() external {
        preApplication.confirmOperatorAddress();
    }

}
