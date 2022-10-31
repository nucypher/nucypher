// SPDX-License-Identifier: AGPL-3.0-or-later

pragma solidity ^0.8.0;


import "contracts/SimplePREApplication.sol";
import "../zeppelin/ownership/Ownable.sol";


contract TestnetThresholdStaking is Ownable {

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

    function setApplication(SimplePREApplication _preApplication) external onlyOwner {
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
        external onlyOwner
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
    function setRoles(address _stakingProvider) external onlyOwner {
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
        external onlyOwner
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
}
