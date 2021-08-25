// SPDX-License-Identifier: GPL-3.0-or-later

pragma solidity 0.8.6;

/**
 * @title IStakingProvider
 * @notice Generic interface for old Staking Contracts
 */
interface IStakingProvider {
    // TODO:  Inherit from IERC165

    // TODO: Events

    /**
     * @dev Penalizes staker `_staker`; the penalty details are encoded in `_penaltyData`
     */
    function slashStaker(address staker, bytes calldata penaltyData) external;

    /**
     * @dev Returns the locked stake amount and unstaking duration for `staker`
     */
    function getStakeInfo(address staker)
        external
        view
        returns (uint256 stakeAmount, uint256 unstakingDuration);
}
