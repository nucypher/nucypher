// SPDX-License-Identifier: GPL-3.0-or-later

pragma solidity 0.8.6;

/**
 * @title IApplication
 * @notice Generic interface for an application
 */
interface IApplication {
    // TODO:  Inherit from IERC165

    // TODO: Events

    function authorizationIncreased(address worker, uint256 amount) external;

    function authorizationDecreaseRequested(address worker, uint256 amount) external;

    function involuntaryAllocationDecrease(address worker, uint256 amount) external;

    /**
     * @dev Get min authorization size from application
     */
    function minAuthorizationSize() external returns (uint256);
}
