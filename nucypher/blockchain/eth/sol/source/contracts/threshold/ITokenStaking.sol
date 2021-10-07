// SPDX-License-Identifier: GPL-3.0-or-later

pragma solidity 0.8.6;

/**
* @notice TokenStaking interface
*/
interface ITokenStaking {
    enum StakingProvider {NU, KEEP, T}

    struct OperatorInfo {
        address owner;
        address payable beneficiary;
        address authorizer;
//        mapping(address => AppAuthorization) authorizations;
//        address[] authorizedApplications;
        uint96 nuStake;
        uint96 keepStake;
        uint96 tStake;
        uint256 startTStakingTimestamp;
    }

    function stakedNu(address) external view returns (uint256);
    function ownerOf(address) external view returns (address);
    function beneficiaryOf(address) external view returns (address payable);
    function approveAuthorizationDecrease(address) external;
    function getMinStaked(address, StakingProvider) external view returns (uint96);
    function authorizedStake(address operator, address application) external view returns (uint96);
    function operatorInfo(address operator) external view returns (OperatorInfo memory);
}
