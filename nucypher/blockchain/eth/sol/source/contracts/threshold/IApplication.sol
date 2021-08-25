// SPDX-License-Identifier: GPL-3.0-or-later

pragma solidity 0.8.6;

/**
 * @title IApplication
 * @notice Generic interface for an application
 */
interface IApplication {
    // TODO:  Inherit from IERC165

    // TODO: Events

    /**
     * @dev Receive call with allocation changes from staking contract
     */
    function receiveAllocation(
        address staker,
        uint256 allocated,
        uint256 allocationPerApp
    ) external;
}
