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
     * @notice Used by T staking contract to inform the application the the authorized amount
     * for the given operator increased. The application may do any necessary housekeeping
     * necessary.
     */
    function authorizationIncreased(address worker, uint256 amount) external;

    /**
     * @notice Used by T staking contract to inform the application that the given operator
     * requested to decrease the authorization to the given amount. The application
     * should mark the authorization as pending decrease and respond to the staking
     * contract with `approveAuthorizationDecrease` at its discretion. Note it may
     * happen right away but it also may happen several months later.
     */
    function authorizationDecreaseRequested(address worker, uint256 amount) external;

    /**
     * @notice Used by T staking contract to inform the application the authorization has
     * been decreased for the given operator to the given amount involuntarily, as
     * a result of slashing. Lets the application to do any housekeeping neccessary.
     * Called with 250k gas limit and does not revert the transaction if
     * `involuntaryAllocationDecrease` call failed.
     */
    function involuntaryAllocationDecrease(address worker, uint256 amount) external;

    /**
     * @dev Get min authorization size from application
     */
    function minAuthorizationSize() external returns (uint256);
}
