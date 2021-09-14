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
     * @dev Receive call with authorization changes from staking contract
     */
    function receiveAuthorization(
        address staker,
        uint256 authorized,
        uint256 deauthorizing,
        uint256 allocationPerApp
    ) external;

    /**
     * @dev Get deauthorization duration from application
     */
    function deauthorizationDuration() external returns (uint256);

    /**
     * @dev Get min authorization size from application
     */
    function minAuthorizationSize() external returns (uint256);
}
