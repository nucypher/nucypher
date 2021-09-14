// SPDX-License-Identifier: GPL-3.0-or-later

pragma solidity 0.8.6;

/**
* @notice TokenStaking interface
*/
interface ITokenStaking {

    enum StakingProvider {NU, KEEP, T}

    // TODO remove
    function authorizedPerApp(address) external view returns (uint256);
    function getAuthorized(address, address) external view returns (uint256, uint256);
    function getAvailableToWithdraw(
        address staker,
        StakingProvider stakingProvider
    ) external view returns (uint256);
    function getBeneficiary(address) external view returns (address);
}
