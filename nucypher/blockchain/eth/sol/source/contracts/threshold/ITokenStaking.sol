// SPDX-License-Identifier: GPL-3.0-or-later

pragma solidity 0.8.6;

/**
* @notice TokenStaking interface
*/
interface ITokenStaking {
    enum StakingProvider {NU, KEEP, T}

    function stakedNu(address) external view returns (uint256);
    function beneficiaryOf(address) external view returns (address payable);
    function approveAuthorizationDecrease(address) external;
    function getMinStaked(address, StakingProvider) external view returns (uint256);
}
